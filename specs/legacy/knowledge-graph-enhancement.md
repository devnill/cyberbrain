# Knowledge Graph Enhancement Spec

**Status:** Draft
**Date:** 2026-03-03
**Depends on:** `mcp_gaps.md` (Gap 8, Gap 9), `enhanced-retrieval.md`

---

## Summary

This spec adds a knowledge graph layer to cyberbrain's Obsidian vault notes. The primary goal is to make beats semantically connected — so that related notes surface each other in retrieval, and so Obsidian's native graph view reflects actual relationships between captured knowledge.

The key research finding that shapes this entire spec: **frontmatter wikilinks appear in Obsidian's backlinks panel (v1.4.5+) but do NOT appear as graph view edges**. Only body wikilinks create graph edges natively, without plugins. This constraint drives the dual encoding strategy below.

The implementation is deliberately incremental. Phase 1 requires no new infrastructure — it reuses the `search_vault()` call already made during autofile and populates fields that already exist. Phase 2 extends the LLM extraction schema to emit typed relations. Phase 3 (deferred) introduces an index for graph traversal in retrieval.

---

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Primary graph encoding** | Body wikilinks under `## Relations` section | Only native Obsidian mechanism that creates graph view edges without plugins |
| **Secondary encoding** | `related:` YAML property (wikilink strings) | Machine-readable; searchable with `[related:value]`; backlinks panel (v1.4.5+); does NOT feed graph view |
| **Relation type representation** | Prefixed prose in body: `- causes [[Note]]` | Fully native; human-readable; no plugin dependency; type survives in text even without tooling |
| **Relation vocabulary source** | Vault CLAUDE.md (authoritative); defaults provided | Consistent with existing vault-adaptive pattern; no hardcoded types in code |
| **Default vocabulary size** | 5 types | Academic PKM research: lean vocabularies (4–8 types) are adopted; larger ones collapse to informal use |
| **LLM relation emission** | Optional field in extraction response | LLM emits relations when evidence exists; missing field means no relations (not an error) |
| **Relation resolution timing** | At write time via `search_vault()` | Avoids post-write pass; `search_vault()` already runs during autofile; minimal overhead |
| **Forward references** | Allowed; stored as-is | Obsidian tracks unresolved links natively; they appear in graph when "Existing files only" is off |
| **Plugin dependency** | None | Hard constraint; everything must work with vanilla Obsidian |
| **Index / database** | Not in this phase | Deferred to `enhanced-retrieval.md` Phase 2 |

---

## Default Relation Vocabulary

Five types, covering the most common semantic relations between captured knowledge. Vault CLAUDE.md may extend or replace this list.

| Relation type | Meaning | Example |
|---|---|---|
| `related-to` | General association; same topic or domain | A caching insight related to a performance decision |
| `causes` | One note's subject leads to or explains another | A problem note causes a decision note |
| `caused-by` | Inverse of causes | A decision was caused-by a problem |
| `supersedes` | This note replaces or obsoletes another | A new approach supersedes an old one |
| `implements` | This note puts another note's concept into practice | A reference note implements an architectural insight |
| `contradicts` | This note challenges or qualifies another | A new insight contradicts a prior assumption |

Use `related-to` as the default when the specific relation type is unknown.

---

## 1. Relation Schema

### Encoding: dual representation

Every beat with relations is encoded in two places:

**A. Body — `## Relations` section** (creates graph edges)

```markdown
## Relations
- causes [[Token Expiry Race Condition]]
- supersedes [[Old Session Management Approach]]
- related-to [[OAuth2 Flow Overview]]
```

- Each line: `- {relation_type} [[Note Title]]`
- Note Title is the exact filename stem (Title Case, no extension)
- This is the ONLY encoding that creates Obsidian graph view edges
- Human-readable; survives without any tooling
- Placed at the end of the body, before any trailing notes

**B. Frontmatter — `related:` property** (backlinks + machine-readable)

```yaml
related:
  - "[[Token Expiry Race Condition]]"
  - "[[Old Session Management Approach]]"
  - "[[OAuth2 Flow Overview]]"
```

- Wikilinks quoted in YAML per Obsidian spec
- Appears in backlinks panel of target notes (v1.4.5+)
- Searchable: `[related:Token Expiry Race Condition]`
- Does NOT create graph edges (confirmed Obsidian limitation)
- Populated with all related note titles regardless of relation type (the type lives in the body)

### Validity constraints

- Relation targets are vault note title stems (the filename without `.md`)
- Same character restrictions as beat titles: no `#`, `[` (except for wikilink syntax), `]`, `^`
- Forward references (titles that don't exist yet) are valid and stored as-is
- Obsidian renders forward references as unresolved links — they appear in graph view when "Existing files only" filter is off
- Maximum 5 relations per beat (lean graph; prevents noise from weak associations)

---

## 2. Frontmatter Changes

### Current frontmatter (unchanged fields)

```yaml
---
id: {uuid}
date: {ISO-8601}
session_id: {session_id}
type: {type}
scope: {project|general}
title: {json-quoted string}
project: {project_name}
cwd: {cwd}
tags: {json-quoted array}
related: []
status: completed
summary: {json-quoted string}
---
```

### Updated frontmatter

```yaml
---
id: {uuid}
date: {ISO-8601}
session_id: {session_id}
type: {type}
scope: {project|general}
title: {json-quoted string}
project: {project_name}
cwd: {cwd}
tags: {json-quoted array}
related:
  - "[[Note Title A]]"
  - "[[Note Title B]]"
status: completed
summary: {json-quoted string}
---
```

**Changes:**
- `related:` changes from `related: []` (hardcoded inline empty list) to a YAML block list of quoted wikilink strings, or `related: []` when no relations are found
- No other frontmatter fields change
- Obsidian Properties UI recognizes list-type properties with wikilink values and renders them as clickable links

### Compatibility with Obsidian Properties UI (v1.4+)

Obsidian v1.4 introduced typed properties. The `related` field should be registered as a **List** type property with **link** subtype. This happens automatically when Obsidian first encounters `- "[[...]]"` values in a list property. The Properties UI will render each entry as a clickable link.

The existing `tags` field already uses a JSON-array format (`["a","b"]`) which Obsidian parses correctly. The `related` field uses YAML block list format instead (more readable for multi-line; both formats parse identically in YAML 1.1).

---

## 3. Extraction Prompt Changes

### `extract-beats-system.md` additions

Add a new section after the existing type vocabulary section:

```
## Relations

After identifying each beat, check whether it has meaningful semantic connections to
other knowledge in the vault. If so, include a `relations` field in the beat JSON.

Relations are optional. Only include them when there is clear semantic evidence.
Do not hallucinate targets — only include relation targets that are explicitly
mentioned or directly implied by the transcript content.

Relation format:
{
  "type": "one of the relation types defined in the vault's CLAUDE.md, or: related-to, causes, caused-by, supersedes, implements, contradicts",
  "target": "Note title as it would appear as a filename (Title Case, no extension, no #[]^)"
}

Include at most 5 relations per beat. Prefer specificity — `causes` is better than
`related-to` when the causal link is clear.

If the vault's CLAUDE.md defines a relation vocabulary, use those types. Otherwise
use the defaults above.

IMPORTANT: Relation targets must be plausible note titles — either names mentioned
in the transcript, prior beats from this session, or concepts that would naturally
exist in a technical knowledge vault. Do not invent abstract targets.
```

### Updated beat JSON schema in `extract-beats-system.md`

```json
{
  "title": "Brief, descriptive title (5-10 words). No #, [, ], or ^.",
  "type": "one of the vault's valid types",
  "scope": "project or general",
  "summary": "Single information-dense sentence optimized for search",
  "tags": ["array", "of", "2-6", "lowercase", "keywords"],
  "body": "Full markdown content. Self-contained. Do not include a Relations section — that is added automatically.",
  "relations": [
    {"type": "causes", "target": "Token Expiry Race Condition"},
    {"type": "related-to", "target": "OAuth2 Flow Overview"}
  ]
}
```

- `relations` is optional. Omit the field (or use `[]`) when no relations apply.
- `body` should NOT include a `## Relations` section — the writer adds it from the `relations` field
- This prevents double-encoding and keeps the LLM from hallucinating wikilink syntax in the body

### `extract-beats-user.md` — no changes required

The vault CLAUDE.md section (injected via `{vault_claude_md_section}`) will include the relation vocabulary when the vault spec is updated (see Section 6). The extraction prompt reads it from there.

---

## 4. Relation Resolution

### At write time (during `write_beat()`)

Relations are resolved and written via two sources, merged:

**Source A — LLM-emitted relations** (from `beat["relations"]` field, if present)
- These are semantic relations the LLM identified from the transcript content
- Targets may or may not exist in the vault yet (forward references are valid)
- Written as-is to `related:` frontmatter and `## Relations` body section

**Source B — `search_vault()` discovery** (existing mechanism, repurposed)
- Already called during `autofile_beat()`; for `write_beat()` (non-autofile path), call it once at write time
- Finds vault notes that textually match the beat's tags and title terms
- Top-3 results used to supplement LLM-emitted relations with `related-to` type
- Excluded if the title matches the beat itself
- Skipped for any target already in Source A (dedup by title)

**Merge logic:**

```python
def resolve_relations(beat: dict, vault_path: str) -> list[dict]:
    """
    Returns merged list of relations: [{type, target}]
    LLM relations take priority; search_vault fills remaining slots up to max 5.
    """
    llm_relations = beat.get("relations", [])
    # Validate: filter any with missing type or target
    validated = [r for r in llm_relations if r.get("type") and r.get("target")]

    # Only supplement with search_vault if there's room
    if len(validated) < 5:
        related_paths = search_vault(beat, vault_path, max_results=5)
        llm_targets = {r["target"].lower() for r in validated}

        for path in related_paths:
            if len(validated) >= 5:
                break
            stem = Path(path).stem
            if stem.lower() not in llm_targets and stem.lower() != beat["title"].lower():
                validated.append({"type": "related-to", "target": stem})
                llm_targets.add(stem.lower())

    return validated[:5]
```

### Forward references

Unresolved targets (note titles that don't exist in the vault) are written as-is. Obsidian tracks them as unresolved links in the Outgoing Links panel and renders them as grey nodes in the graph view when "Existing files only" is off.

No forward reference resolution pass is needed. If the target note is later created (by cyberbrain or manually), Obsidian resolves the link automatically by title matching.

### Autofile path

When `autofile_beat()` is called, `search_vault()` is already invoked for routing context. The same results are passed through to `resolve_relations()` so no second grep pass is needed. The autofile LLM response (action: create) produces a full note with frontmatter; the relations are injected into that frontmatter and body before writing.

---

## 5. Retrieval Impact

### `cb_recall` (immediate, without index)

With `related:` populated in frontmatter, the Obsidian `[related:value]` search syntax becomes usable. `cb_recall` can support a `--related-to <title>` filter:

```bash
grep -r -l "related:" "$VAULT_PATH" | \
  xargs grep -l "$TITLE" | \
  head -n $MAX_RESULTS
```

Or using native Obsidian search syntax injected into the output as a suggestion:
`Search Obsidian: [related:Note Title]`

Additionally, when `cb_recall` returns a note, it can now surface its `related:` field to the AI so the AI can suggest following the graph: "This note relates to [[Token Expiry Race Condition]] — fetch that too?"

### `cb_read` (new tool, from mcp_gaps.md Gap 1)

When `cb_read` is implemented, it should:
1. Parse `related:` frontmatter and extract linked note titles
2. Include a `## Related notes` section in its output listing those titles and their summaries
3. Allow the AI to decide whether to follow the chain

### `cb_recent` (new tool, from mcp_gaps.md Gap 3)

No direct impact on relations. But notes from the same session share a `session_id` — `cb_recent` can use this to surface "other notes from this session" as implicit relations without needing the graph.

### Phase 2 (from enhanced-retrieval.md) — search index

Once the SQLite FTS5 + embedding index is built, the `related:` frontmatter values can be indexed as relation edges. This enables:
- "Find all notes that reference `[[Token Expiry Race Condition]]`"
- Relation-type filtering: "Find notes that `causes` anything related to auth"
- Graph traversal in `cb_recall`: follow N hops via `related:` edges

This is additive — the frontmatter schema defined here is the correct substrate for that future index.

---

## 6. Vault CLAUDE.md Contract

The `/cb-setup` skill generates the vault's `CLAUDE.md`. That file is authoritative for type vocabulary, tag conventions, and filing rules. It should also be authoritative for the relation vocabulary.

### Required additions to the `cb-setup`-generated CLAUDE.md

Add a `## Knowledge Graph` section (mandatory for all vault types):

```markdown
## Knowledge Graph

### Relation Vocabulary

Cyberbrain (`/cb-extract`, `/cb-file`, `/cb-recall`) uses these relation types when
linking beats. The relation type appears as a prefix before the wikilink in the
`## Relations` section of each note body, and all related titles are listed in the
`related:` frontmatter property.

| Relation type | Meaning |
|---|---|
| `related-to` | General association; same topic or domain |
| `causes` | This note's subject leads to or explains the target |
| `caused-by` | The target causes or explains this note's subject |
| `supersedes` | This note replaces or obsoletes the target |
| `implements` | This note puts the target concept into practice |
| `contradicts` | This note challenges or qualifies the target |

To customize: replace or extend this table. Cyberbrain reads this section and passes
it to the extraction LLM as the authoritative relation vocabulary.

### Linking Rules

- Relation targets must be exact note title stems (the filename without `.md`)
- Maximum 5 relations per beat
- Use `related-to` when the specific type is unclear
- Forward references (notes that don't exist yet) are valid — Obsidian resolves
  them when the target note is created
- Do not add a `## Relations` section manually to beats — it is managed by cyberbrain
```

### How `cb-setup` generates this section

The `/cb-setup` skill currently generates 14 required sections. This adds one more. The skill should:
1. Read any existing relation vocabulary from the vault's CLAUDE.md (if updating, preserve custom types)
2. Use the default vocabulary above if no existing section is found
3. Include the section unconditionally (all vault archetypes benefit from it)

### How cyberbrain reads it

The extraction prompt already injects `{vault_claude_md_section}` into both extraction and autofile prompts. The relation vocabulary section will be included automatically in that injection. No code change needed to pass it to the LLM.

The `resolve_relations()` function does not need to read the vault CLAUDE.md directly — the LLM uses the vocabulary at extraction time. If a custom vocabulary is defined, the LLM emits those types; they are written as-is.

---

## 7. Constraints

All implementations must satisfy:

- **No plugin dependency.** The schema must work in vanilla Obsidian. The `## Relations` body section creates graph edges natively. The `related:` frontmatter creates backlinks natively (v1.4.5+). No community plugins are assumed.
- **Additive only.** Existing beats without `relations` in their extraction JSON, or with `related: []` in frontmatter, remain valid and are not re-extracted or modified. The enhanced schema is a superset.
- **Wikilink title format.** Relation targets must be note title stems in Title Case (matching the filename without extension). This is the format Obsidian uses for wikilink resolution. Do not use file paths or `[[folder/title]]` format — shortest-path title resolution is Obsidian's default and cyberbrain's convention.
- **No separate database or daemon.** Relation data lives in the Markdown files themselves. The SQLite index from `enhanced-retrieval.md` is a future enhancement that reads this data; it is not required for relations to function.
- **Graceful degradation.** If `search_vault()` returns no results and the LLM emits no relations, the note is written with `related: []` and no `## Relations` section. This is identical to current behavior.
- **Non-fatal on resolution failure.** If `resolve_relations()` raises an exception (grep failure, I/O error), it logs a warning and returns `[]`. The write proceeds without relations rather than failing.

---

## 8. Migration and Rollout

### Existing beats

Existing beats have `related: []` and no `## Relations` body section. They are valid under the new schema — no migration is required for them to remain functional.

Backfilling existing beats is optional and supported via `/cb-enrich`.

### `/cb-enrich` additions for backfill

The enrich skill should support a `--add-relations` flag (or include it in a future pass):

1. Scan vault notes with `related: []` (or no `related:` field)
2. For each note: call `search_vault()` with the note's tags and title terms
3. Populate `related:` frontmatter with top-3 results as wikilinks
4. Append a `## Relations` body section with `- related-to [[Title]]` entries for each
5. Respect `--dry-run`, `--folder`, `--limit`, `--since` flags
6. Skip notes with `enrich: skip` frontmatter

This is a purely additive pass — it does not modify any existing frontmatter fields. It cannot emit typed relations (only `related-to`) because it doesn't have LLM extraction context. Typed relations are only emitted at extraction time.

### `extract_beats.py` changes required

1. **`write_beat()` function** — update to:
   - Accept relations from beat dict (`beat.get("relations", [])`)
   - Call `resolve_relations(beat, vault_path)` to merge LLM + search results
   - Write populated `related:` frontmatter (wikilink format) instead of `related: []`
   - Append `## Relations` section to body if relations list is non-empty

2. **Beat JSON parsing** — update validation block to:
   - Accept optional `relations` field (list of `{type, target}` dicts)
   - Filter out malformed relation objects (missing type or target)
   - Cap at 5 relations
   - Validate target titles: strip `#[]^`, truncate to 80 chars (reuse `make_filename` logic minus `.md`)

3. **`autofile_beat()` function** — update to:
   - Pass already-fetched `search_vault()` results to `resolve_relations()` to avoid second grep
   - When action is `create`: inject relations into the `content` string before writing
   - When action is `extend`: no frontmatter modification (extending an existing note doesn't add the beat's relations to the parent note)

4. **New function: `resolve_relations()`** — as specified in Section 4

5. **New function: `format_relations_section(relations: list[dict]) -> str`**

```python
def format_relations_section(relations: list[dict]) -> str:
    """Format relations as a ## Relations body section."""
    if not relations:
        return ""
    lines = ["## Relations"]
    for r in relations:
        lines.append(f"- {r['type']} [[{r['target']}]]")
    return "\n".join(lines) + "\n"
```

6. **New function: `format_related_frontmatter(relations: list[dict]) -> str`**

```python
def format_related_frontmatter(relations: list[dict]) -> str:
    """Format relations as YAML frontmatter list."""
    if not relations:
        return "related: []"
    lines = ["related:"]
    seen = set()
    for r in relations:
        title = r["target"]
        if title not in seen:
            lines.append(f'  - "[[{title}]]"')
            seen.add(title)
    return "\n".join(lines)
```

### Extraction prompt files

- `prompts/extract-beats-system.md` — add Relations section (Section 3)
- `prompts/extract-beats-user.md` — no changes
- `prompts/autofile-system.md` — no changes (autofile doesn't emit relations)
- `prompts/autofile-user.md` — no changes

### Vault CLAUDE.md template

The `/cb-setup` skill's CLAUDE.md generator (in `skills/cb-setup/SKILL.md` Phase 4) must include the `## Knowledge Graph` section as a mandatory output section.

---

## Before / After Examples

### Beat frontmatter — before

```yaml
---
id: f47ac10b-58cc-4372-a567-0e02b2c3d479
date: 2026-03-03T14:22:41Z
session_id: abc12345
type: decision
scope: project
title: "Chose RS256 over HS256 for JWT Signing"
project: auth-service
cwd: /Users/dan/code/auth-service
tags: ["jwt", "authentication", "security", "signing"]
related: []
status: completed
summary: "Selected RS256 asymmetric signing for JWTs to allow public key verification by downstream services without sharing the secret."
---

## Chose RS256 over HS256 for JWT Signing

Selected RS256 (asymmetric RSA) over HS256 (symmetric HMAC) for JWT signing.
This allows downstream services to verify tokens using the public key without
needing access to the signing secret.

The tradeoff is larger token size and slower signing, acceptable given the
security benefit and the multi-service architecture.
```

### Beat frontmatter — after (with relations)

```yaml
---
id: f47ac10b-58cc-4372-a567-0e02b2c3d479
date: 2026-03-03T14:22:41Z
session_id: abc12345
type: decision
scope: project
title: "Chose RS256 over HS256 for JWT Signing"
project: auth-service
cwd: /Users/dan/code/auth-service
tags: ["jwt", "authentication", "security", "signing"]
related:
  - "[[Token Expiry Race Condition]]"
  - "[[JWT Token Refresh Flow]]"
  - "[[Multi-Service Auth Architecture]]"
status: completed
summary: "Selected RS256 asymmetric signing for JWTs to allow public key verification by downstream services without sharing the secret."
---

## Chose RS256 over HS256 for JWT Signing

Selected RS256 (asymmetric RSA) over HS256 (symmetric HMAC) for JWT signing.
This allows downstream services to verify tokens using the public key without
needing access to the signing secret.

The tradeoff is larger token size and slower signing, acceptable given the
security benefit and the multi-service architecture.

## Relations
- caused-by [[Token Expiry Race Condition]]
- implements [[Multi-Service Auth Architecture]]
- related-to [[JWT Token Refresh Flow]]
```

**What each encoding enables natively (no plugins):**

| Encoding | Obsidian graph edge | Backlinks panel | `[related:value]` search |
|----------|--------------------|-----------------|--------------------|
| `related:` frontmatter | No | Yes (v1.4.5+) | Yes |
| `## Relations` body | Yes | Yes | No (body search only) |

The `## Relations` body section is the only way to get graph edges. The `related:` frontmatter is the only way to get typed-query search. Both are needed; neither alone is sufficient.

---

## Out of Scope

The following are explicitly deferred:

- **SQLite Relations table** — the graph traversal index from `enhanced-retrieval.md` Phase 2. The frontmatter schema defined here is the substrate; the index reads from it.
- **`build_context`-style traversal tool** — requires the index above. Deferred.
- **Relation type validation at write time** — the code checks that type and target fields exist but does not validate the type string against the vault vocabulary. The LLM is responsible for using the correct vocabulary from the system prompt. Hard validation at write time would require reading the vault CLAUDE.md on every write, adding latency.
- **Bidirectional relation maintenance** — when Note A declares `causes [[Note B]]`, Note B is not automatically updated to declare `caused-by [[Note A]]`. Bidirectional maintenance would require reading and editing existing vault notes on every write — too invasive. Obsidian's backlinks panel provides the reverse direction natively.
- **Canvas-based graph visualization** — Canvas edges support free-text labels but no typed edge schema (confirmed: JSON Canvas 1.0 spec has `label` string only, no `type` field). Canvas is useful for manual visualization but not suitable as the primary relation storage format.
