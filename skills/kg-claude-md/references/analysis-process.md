# Vault Analysis Process

Detailed instructions for crawling an Obsidian vault and extracting the information
needed to generate an accurate, vault-specific CLAUDE.md.

---

## Guiding Principles for This Analysis

**Counts and percentages are internal analysis tools only.** All frequency data collected
during this process (note counts per folder, percentage of notes with a given field,
orphan rates, etc.) is used to determine what rules to write — it must never appear
verbatim in the generated CLAUDE.md. The output describes patterns and rules, not the
current state of the vault.

**Ask, don't infer.** When analysis reveals an ambiguity — conflicting conventions, unclear
overlap between types, inconsistent tag usage — stop and ask the vault owner for the
intended rule before generating that section. Do not make a judgment call and mark it as
"inferred". Ask one question at a time, wait for the answer, then continue.

---

## Phase 1 — Structural Survey

### 1.1 Top-Level Scan

List the vault root directory. Record:
- Every top-level folder name
- File count per folder (use recursive listing)
- Any markdown files at the root level

Look for and read if present:
- `CLAUDE.md` — existing guidance to preserve/update
- `README.md` — may contain the user's own vault documentation
- `.obsidian/` — skip contents but note its presence (confirms this is an Obsidian vault)

### 1.2 Folder Convention Inference

From folder names, determine:

- **Naming style**: kebab-case (`project-notes/`), Title Case (`Project Notes/`), type-named (`project/`, `concept/`), date-prefixed (`2025-01/`), or flat (everything at root)
- **Organization principle**: by entity type? by domain/topic? by time? by status? or mixed?
- **Depth**: how many levels of nesting exist?

Record your inference — it directly shapes the "Folder Structure" section of CLAUDE.md.

### 1.3 Special Folder Detection

Flag these folder patterns if found:
- `_inbox/`, `inbox/`, `00-inbox/` — capture/triage area
- `_templates/`, `templates/` — note templates
- `archive/`, `_archive/` — retired content
- `attachments/`, `assets/` — non-markdown files
- `daily/`, `journal/`, `log/` — temporal notes
- `MOC/`, `maps/`, `index/` — index or map-of-content notes

---

## Phase 2 — Frontmatter Sampling

### 2.1 Note Selection

Select notes to sample using this priority order:

1. **All notes in folders named by entity type** (e.g., `insight/`, `decision/`, `concept/`) — read all if <30 total
2. **Index / MOC notes** — always read fully; they often describe the intended structure
3. **Random spread** — fill remaining sample budget with notes from diverse folders

Never sample only from one folder. Diversity of sample is more important than size.

### 2.2 Per-Note Extraction

For each sampled note, extract:

```
file: <path relative to vault root>
frontmatter_keys: [list of all YAML keys present]
frontmatter_values: {key: example_value} for each key
has_body: true/false
wikilinks: [list of all [[...]] patterns found]
inline_tags: [list of #tag patterns in body]
frontmatter_tags: [list from tags: field]
link_context: [1-2 example sentences containing wikilinks, to assess relationship expression]
word_count: approximate
```

### 2.3 Schema Aggregation

After sampling, aggregate across all notes. These are **internal analysis data** — use them
to determine what rules to write, but never include counts or percentages in the output.

**Key frequency table** — for each frontmatter key:
```
key: type
  prevalence: universal | common | occasional | rare
  value_types: [string, list, date, boolean, ...]
  example_values: [up to 3 distinct examples]
  consistency_issues: [e.g., "mixed date formats: YYYY-MM-DD and MM/DD/YYYY"]
```

**Entity type inventory** — values of the `type:` field:
```
type_value:
  prevalence: dominant | secondary | rare
  example_files: [2-3 representative paths]
  common_fields: [fields present in most notes of this type]
  missing_fields: [fields common in other types but absent here]
```

**Domain inventory** — values of the `domain:` field or equivalent tag/folder:
```
domain_value:
  prevalence: primary | secondary | sparse
  entity_types_present: [which types appear in this domain]
```

**Tag taxonomy**:
```
tag: #status/active
  prevalence: established | occasional | singleton
  notes_using: [sample of 2-3 paths]
```
Group by prefix if nested tags are in use (`#status/`, `#domain/`, `#priority/`, etc.)

### 2.4 Effective Schema Determination

From the aggregation, classify each field qualitatively — do not include the thresholds
or counts in the output:

- **Universal fields**: present in nearly all notes — treat as effectively required
- **Type-specific required fields**: consistently present in one type, rare elsewhere
- **Optional fields**: present but not consistent — include in schema marked optional
- **Experimental fields**: rare, no clear pattern — note as "in use by some notes, not yet standardized"
- **Inconsistent fields**: same key, incompatible value formats — flag as needing normalization

**If the schema is ambiguous** (e.g., two types appear to overlap in meaning), ask the vault
owner to clarify the intended distinction before writing those type sections.

---

## Phase 3 — Link and Relationship Pattern Analysis

### 3.1 Wikilink Style

From the collected wikilink data, determine:
- Are paths used (`[[folder/note]]`) or bare names (`[[note]]`)?
- Are aliases used (`[[note|Display Name]]`)?
- Are links to folders/indexes used (`[[concept/]]`)?

Identify the dominant pattern and note any mixing.

### 3.2 Relationship Expression

Look at the `link_context` samples (sentences containing wikilinks).

**High-quality pattern** — relationship expressed in prose:
> "This decision was made to address [[problem/ctcss-false-triggers]]"
> "The technique is an instance of [[concept/goertzel-algorithm]]"

**Low-quality pattern** — bare link with no relationship context:
> "Related: [[some-note]]"
> "See also [[concept/fft]]"

Record which pattern dominates. This informs the linking guidance section.

### 3.3 Frontmatter Relationship Arrays

Check whether notes use structured relationship fields like:
- `related:`, `caused-by:`, `resolves:`, `applies-to:`, `learned-from:`, `used-in:`

If present: note which relationship types are in use and what they link to.
If absent: note that relationships are expressed only through prose + wikilinks.

### 3.4 Index / MOC Notes

If index or MOC notes exist, read them fully. They often contain:
- Curated lists of notes by type or domain (reveals intended organization)
- The user's own written descriptions of their ontology
- Dataview queries (reveals what fields they query on)

Extract any Dataview queries and record what fields they reference — these are the de-facto required fields for the vault's workflows.

---

## Phase 4 — Gap and Inconsistency Detection

Run these checks and record findings, prioritized by impact. These are **internal analysis
findings** — they inform what to write in Known Issues, but must be expressed as pattern
descriptions, not counts. Ask the vault owner about any ambiguous findings before writing.

### Naming Conventions
- Identify the dominant naming style
- If a significant minority of notes use a different style, flag as an inconsistency
- In the output: describe the correct convention and note the inconsistency as a pattern

### Orphan Notes
- Notes with 0 outgoing wikilinks and not in `inbox/` or `daily/` folders
- If this is pervasive across the vault, note it as a systematic gap in Known Issues

### Missing Required Fields
- For each entity type: are notes of that type consistently missing fields that are
  otherwise standard? This indicates a schema gap, not individual anomalies.
- Only report as an issue if it is a consistent pattern for a type, not individual outliers.

### Tag Singletons
- Tags used only once — likely accidental or deprecated
- Report as a pattern (e.g., "auto-generated `project/` tags are noise") not as a list

### Date Format Inconsistency
- Mixed `YYYY-MM-DD`, `MM/DD/YYYY`, or plain year values in the same field
- Flag if found — date consistency is critical for Dataview queries

### Undefined Entity Types
- Notes without a `type:` field when it is otherwise standard
- Notes where `type:` value doesn't match any established pattern
- **If types appear to overlap**, ask the vault owner to clarify boundaries before writing

---

## Synthesis Notes

Before writing the CLAUDE.md, form an overall characterization of the vault. These are
internal framing tools to guide tone and emphasis — do not include them verbatim in output.

**Maturity level:**
- *Nascent* (very few notes, inconsistent schema, few links): Focus CLAUDE.md on establishing patterns
- *Developing* (schema emerging, some consistency): Focus on consistency and link density
- *Established* (clear schema, many notes): Focus on extension guidance and maintenance

**Schema state:**
- *Implicit*: conventions exist but aren't formally defined anywhere
- *Partially explicit*: some types have clear schemas, others don't
- *Explicit*: type schemas are consistent and could be documented directly

**Primary user workflow** (derive from note types and any Dataview queries found):
- Project-centric: most notes relate to active projects
- Knowledge-centric: most notes are concepts, insights, resources
- Whole-life PKM: covers both professional and personal domains

**Vault scope:**
- *Domain-specific*: vault is dedicated to one project or domain — it's appropriate to
  reference specific areas in filing guidance
- *General-purpose*: vault covers many domains and grows over time — filing guidance must
  be expressed as patterns and rules, never as a lookup table of current specific areas

This characterization shapes the tone and emphasis of the CLAUDE.md. If the scope or
workflow is unclear, ask the vault owner before writing.

**Final check before writing:** Identify any ambiguities that require clarification from the
vault owner and ask them now, one at a time. Do not proceed to Step 4 of the skill with
unresolved questions.
