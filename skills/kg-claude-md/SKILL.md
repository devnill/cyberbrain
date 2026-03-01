---
name: kg-claude-md
description: >
  Analyze an Obsidian knowledge graph vault and generate a CLAUDE.md file that provides
  prescriptive guidance for adding and curating notes in that vault. Use this skill whenever
  the user wants to generate, update, or regenerate a CLAUDE.md for their Obsidian vault,
  or when they ask Claude to understand their vault structure, document their knowledge graph
  conventions, or produce instructions for working within their PKM system. Triggers include:
  "generate a CLAUDE.md for my vault", "analyze my vault", "document my vault conventions",
  "create filing instructions for my notes", "update my CLAUDE.md", "what are my vault patterns".
  Always use this skill when the task involves reading an Obsidian vault to produce guidance
  or documentation about it.
compatibility: "Requires filesystem access to read the Obsidian vault. Python 3 must be available for analyze_vault.py."
---

# Vault Analyzer → CLAUDE.md Generator

Reads an Obsidian vault, runs automated structural analysis, deep-samples selected notes,
and produces a `CLAUDE.md` at the vault root that serves as authoritative guidance for
adding, curating, and extending the vault's knowledge graph.

The output has two purposes:
1. **Working within existing patterns** — entity types, required fields, naming conventions, tag vocabulary, link style
2. **Extending the ontology** — explicit criteria and process for adding new types, domains, tags, and fields

---

## Step 0 — Setup

If the vault path is not provided, ask for it before proceeding.

Verify the path is accessible and is an Obsidian vault (check for `.obsidian/` directory or
a significant number of `.md` files). If access fails, tell the user and stop.

Check whether a `CLAUDE.md` already exists at the vault root. If it does, read it before
generating — preserve any custom sections the user has added.

---

## Step 1 — Run the Vault Analyzer Script

The `scripts/analyze_vault.py` script performs a full structural scan without requiring
manual file reads. Locate the script using the Bash tool, then run it:

```bash
# Try installed path first, then plugin-mode path
ls ~/.claude/skills/kg-claude-md/scripts/analyze_vault.py 2>/dev/null \
  || ls "${CLAUDE_PLUGIN_ROOT}/skills/kg-claude-md/scripts/analyze_vault.py" 2>/dev/null
```

Use whichever path exists. If neither exists, tell the user:
"The analyze_vault.py script was not found. Run `bash install.sh` from the
knowledge-graph repository to reinstall."

Also verify pyyaml is available:
```bash
python3 -c "import yaml" 2>/dev/null || pip install pyyaml -q
```

Then run the script with the resolved path:
```bash
python3 <resolved_path> "<vault_path>" --output /tmp/vault_report.json
cat /tmp/vault_report.json
```

The script produces a JSON report containing:
- `total_notes` — total markdown file count
- `folder_structure` — top-level folders with note counts, depth distribution
- `naming_conventions` — distribution of naming styles (kebab-case, Title Case, etc.)
- `entity_types.distribution` — counts per `type:` frontmatter value
- `entity_types.samples` — example file paths per type
- `domains` — counts per `domain:` frontmatter value
- `statuses` — counts per `status:` frontmatter value
- `frontmatter.field_usage` — every frontmatter field with note count and top values
- `tags.top_tags` — all tags with frequencies
- `tags.hierarchy` — tag namespace groupings
- `links.hub_nodes` — most-linked notes (graph centers)
- `links.notes_with_no_outgoing_links` — count of notes with no wikilinks
- `links.notes_with_no_incoming_links` — count of orphan notes
- `links.orphan_sample` — up to 10 example orphan paths

Use this report as the primary data source for the analysis phases below.

---

## Step 2 — Deep-Read Selected Notes

The script gives you statistics; now read actual note content to understand quality and patterns.

**Priority order for what to read:**
1. Hub nodes from `links.hub_nodes` — these anchor the graph
2. Index / MOC notes (names like `index`, `map`, `MOC`, `_index`)
3. 2–3 notes per entity type from `entity_types.samples`
4. Any notes containing Dataview queries (reveal which fields are queried)
5. The vault README if present

**Scale to vault size:**

| Vault size | Notes to deep-read |
|---|---|
| <50 notes | Read all |
| 50–200 | 25–35: all hub/index notes + samples across every entity type |
| 200–500 | 40–50: all hub/index notes + 3–5 per entity type |
| 500+ | 60–80: all hub/index notes + 2–3 per type, weight toward high-link-count notes |

**From each note, extract:**
- Body quality: well-formed vs. sparse stubs
- Link style: `[[bare]]`, `[[folder/name]]`, or `[[name|alias]]`
- Whether wikilinks carry relationship context in surrounding prose, or are bare
- Relationship arrays in frontmatter (`caused-by:`, `resolves:`, `applies-to:`, etc.)
- Recurring body structure (headers, sections) that suggest an implicit template

---

## Step 3 — Synthesize Findings

Before writing, form a clear picture on each of these. All quantitative data from Step 1
is for **internal analysis only** — counts, percentages, and frequencies must never
appear in the generated CLAUDE.md.

### Effective Schema
From `frontmatter.field_usage`, classify each field qualitatively:
- **Universal** (present in nearly all notes) → required for all types
- **Type-specific** (common in one type, rare elsewhere) → required for that type
- **Optional** (present but not consistent) → include in schema, marked optional
- **Experimental** (rare, no clear pattern) → note as "in use by some notes, not yet standardized"

### Naming Convention
Identify the dominant style from `naming_conventions`. If there is a significant minority
of notes using a different style, flag it as an inconsistency to address going forward.

### Tag System
Established namespaces from `tags.hierarchy`. Tag singletons are likely accidental —
list the singleton *namespaces or patterns* (not individual tags) as consolidation
candidates in Known Issues.

### Gaps and Inconsistencies
Surface the top 3–5 most impactful **systematic** issues only — issues that affect a
whole class of notes or a pattern, not one-off anomalies:
- Entity types consistently missing required fields
- Sparse cross-linking across the vault
- Naming style inconsistency
- Date format inconsistency
- Notes missing `type:` when it is otherwise universal

### Vault Maturity
- **Nascent** (very few notes, inconsistent schema): Focus on establishing patterns
- **Developing** (schema emerging, some consistency): Focus on consistency and link density
- **Established** (clear schema, many notes): Comprehensive coverage, extension rules

---

## Step 4 — Generate the CLAUDE.md

Read `references/output-structure.md` for full section definitions, content requirements,
and writing guidelines before generating.

The CLAUDE.md must follow this section order:

1. Vault Overview
2. Folder Structure
3. Entity Types *(one subsection per established type)*
4. Domain Taxonomy
5. Tagging Conventions
6. Linking Conventions
7. File Naming and Organization
8. Hub Notes and Index Structure *(if MOC/index notes exist)*
9. Extending the Ontology *(mandatory)*
10. Quality and Maintenance Rules
11. Claude-Specific Behaviors
12. Known Issues *(only if significant gaps found)*

**Non-negotiable requirements:**

- Ground all content in vault findings — use the vault's actual type names, domain names,
  tag values, and field names. Do not import vocabulary from outside the vault.
- Flag inferred conventions: `*(inferred — verify with vault owner)*`
- The **Extending the Ontology** section is mandatory. It prevents schema sprawl by giving
  clear criteria for when a new type, domain, field, or tag is warranted vs. when existing
  structures should be reused.
- Write in imperative mood: "Use X", "Always include Y", "Do not Z". Not hedged suggestions.
- Every entity type section needs a concrete YAML frontmatter example with realistic values.
- **Never include specific note counts, percentages, or frequencies.** These go stale
  immediately and add noise without helping Claude make filing decisions. Describe patterns
  and rules, not the current state of the vault.
- **Describe folder structure using structural patterns, not by enumerating specific area
  names.** Write `Work/Projects/<project-name>/` rather than listing `Work/Projects/hermes/`,
  `Work/Projects/gkls/`, etc. The goal is to teach the filing rule, not map the current vault.
  Only name a specific folder when it is a first-class structural concept (e.g., `Work/Inbox/`,
  `Assets/templates/`) — not when it is one instance of a pattern.
- **When the vault is a general-purpose PKM (not dedicated to a single project), keep
  guidance domain-agnostic.** Do not reference specific project names, people, or content
  areas as navigation guides. Describe the types and rules that apply universally; Claude can
  derive where a specific piece of content belongs from those rules.
- **Every rule must be systematic.** If a convention only applies to one specific note or area
  and cannot be generalized, omit it. The CLAUDE.md teaches durable filing behaviour, not
  catalogues of exceptions.

---

## Step 5 — Save and Report

Save the generated CLAUDE.md to the vault root: `<vault_path>/CLAUDE.md`

Report to the user:
1. **Summary** — note count, entity types found, vault maturity assessment
2. **Top gaps detected** — list up to 5, one line each
3. **Where it was saved**
4. **One recommended next action**

---

## Reference Files

- `references/output-structure.md` — Full section definitions, content requirements, tone
  guidelines, and what CLAUDE.md is/isn't. **Read before Step 4.**
- `references/claude-md-template.md` — Compact section specs and field formatting reference.
- `scripts/analyze_vault.py` — Vault analyzer. Run in Step 1.
