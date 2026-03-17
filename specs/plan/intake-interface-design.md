# Intake Interface Design

## Current State Analysis

### cb_extract (extract.py)

**Purpose:** Extract beats from a conversation transcript file.

**Parameters:**
- `transcript_path: str` — path to a `.jsonl` transcript file (must be within `~/.claude/projects/`)
- `session_id: str | None` — optional dedup key (defaults to file stem)
- `cwd: str | None` — project directory for scoped routing

**Behavior:** Reads a transcript file, parses JSONL, truncates to 150K chars, calls `_extract_beats()` (LLM extraction), then writes each beat via `write_beat()` or `autofile_beat()`. Returns a summary of created notes.

**Use case:** Session extraction — process a complete Claude Code transcript to capture durable knowledge.

### cb_file (file.py)

**Purpose:** File a specific piece of information into the vault.

**Parameters:**
- `content: str` — the text to file
- `type_override: str | None` — force a specific note type
- `folder: str | None` — vault-relative folder to file into
- `cwd: str | None` — project directory for scoped routing

**Behavior:** Takes arbitrary text content, calls `_extract_beats()` (the same LLM extraction pipeline as cb_extract), applies optional type override, then writes via `write_beat()` or `autofile_beat()`. Returns confirmation with title, type, tags, path.

**Use case:** Single-beat capture — "save this", "file this" during a live session.

### Overlap and Redundancy

The two tools share almost identical post-extraction logic:

1. Both call `_extract_beats()` with the same backend pipeline
2. Both have the same autofile/write_beat branching logic (lines 87-118 in extract.py, lines 70-103 in file.py)
3. Both have the same vault_context caching for autofile (identical blocks)
4. Both have the same journal entry logic
5. Both route via `cwd` the same way

The only real differences:
- **Input source:** cb_extract reads from a transcript file; cb_file takes inline text
- **Security:** cb_extract restricts transcript_path to `~/.claude/projects/`
- **Folder override:** cb_file has it; cb_extract does not
- **Type override:** cb_file has it; cb_extract does not
- **Source tag:** cb_extract uses `"hook-extraction"`; cb_file uses `"manual-filing"`

Neither tool covers use case 3 (document intake) — filing a pre-written document without LLM extraction. Both tools always run through `_extract_beats()`, which means even a perfectly structured document gets reprocessed by the LLM.

## Use Cases

### UC1: Session Extraction

**Trigger:** User asks to process a transcript, or automatic hook fires.

**Input:** A `.jsonl` transcript file path from `~/.claude/projects/`.

**Pipeline:** Parse transcript -> LLM extraction -> multiple beats -> write each to vault.

**Key requirements:** File path security (restrict to `~/.claude/projects/`), transcript truncation, multi-beat output, dedup via session_id.

### UC2: Single-Beat Capture

**Trigger:** User says "save this", "file this", "remember this" during a live session.

**Input:** A description or snippet of text to preserve.

**Pipeline:** Text -> LLM extraction (typically produces 1 beat) -> write to vault.

**Key requirements:** Minimal friction, type/folder override, fast feedback. The LLM extraction step is valuable here because it classifies, titles, tags, and structures the content.

### UC3: Document Intake

**Trigger:** User has a pre-written document (research report, structured notes, reference material) to file into the vault.

**Input:** A complete document (title, body, optionally tags and type).

**Pipeline:** Assemble frontmatter -> route to folder (explicit or autofile) -> write to vault -> update index.

**Key requirements:** No LLM extraction step. The document is already structured. The system adds frontmatter, routes it, and indexes it. This is a write-through to the vault with metadata enrichment, not a knowledge extraction operation.

## Proposed Tool Set

### Tool 1: `cb_extract` (retained, unchanged)

**Purpose:** Extract knowledge beats from a conversation transcript file.

**Parameters:** (unchanged)
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `transcript_path` | `str` | required | Path to `.jsonl` transcript. Must be within `~/.claude/projects/`. |
| `session_id` | `str \| None` | `None` | Optional dedup key. Defaults to transcript file stem. |
| `cwd` | `str \| None` | `None` | Project directory for scoped routing. |

**Return value:** Summary listing each beat created (title, type, vault path), or "No beats extracted."

**Use cases covered:** UC1 (session extraction).

**Rationale for keeping separate:** Session extraction has unique requirements (file path security boundary, JSONL parsing, transcript truncation, multi-beat output) that don't apply to the other use cases. Merging it into a generic tool would either bloat the parameter surface or require a mode flag, both of which violate the "zero ceremony" principle.

### Tool 2: `cb_file` (expanded to cover UC2 and UC3)

**Purpose:** File content into the knowledge vault — either a description to be extracted by LLM (single-beat capture) or a pre-written document (document intake).

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `content` | `str` | required | The content to file. For single-beat capture: a description of the knowledge. For document intake: the full document body. |
| `title` | `str \| None` | `None` | Note title. **When provided, skips LLM extraction** — the content is filed directly as a vault note. When omitted, the content is passed through LLM extraction for classification, titling, and tagging. This is the mode switch between UC2 and UC3. |
| `type` | `str \| None` | `None` | Note type (e.g. `reference`, `decision`). For document intake: defaults to `reference`. For single-beat capture: overrides LLM classification if provided. |
| `tags` | `str \| None` | `None` | Comma-separated tags. For document intake: applied as-is. For single-beat capture: merged with LLM-generated tags. |
| `durability` | `str \| None` | `None` | Durability for document intake (UC3). Defaults to `"durable"`. Ignored for single-beat capture (UC2) — the LLM decides. Controls routing: `"working-memory"` sends the note to the Working Memory folder; `"durable"` routes to inbox or project folder per normal scope logic. |
| `folder` | `str \| None` | `None` | Vault-relative folder path. Overrides autofile and default routing when provided. |
| `cwd` | `str \| None` | `None` | Project directory for scoped routing. |

**Return value:** Confirmation with the note title, type, tags, and vault path where it was filed.

**Use cases covered:** UC2 (single-beat capture), UC3 (document intake).

**Mode logic:**
- `title` is `None` → **Single-beat capture** (UC2). Content goes through `_extract_beats()`, same as today. `type` acts as type_override. `tags` are merged with LLM output.
- `title` is provided → **Document intake** (UC3). No LLM extraction. Assemble a beat dict from the provided fields (`title`, `content` as body, `type` defaulting to `reference`, `tags`). Generate frontmatter. Write via `write_beat()` or `autofile_beat()` (if autofile enabled and no explicit `folder`). Update search index.

**Parameter rename:** `type_override` becomes `type`. The `_override` suffix is unnecessary — the parameter's behavior is clear from context and the docstring. In UC3 mode it's the primary type, not an override.

## Tools Removed

None. The tool count does not increase.

- `cb_extract` — retained, unchanged
- `cb_file` — retained, expanded (no new tool)

### Parameters Changed

The following interface changes are introduced in this proposal:

| Parameter | Change | Notes |
|-----------|--------|-------|
| `type_override` → `type` | **Renamed** (breaking) | Any caller using `cb_file(type_override=...)` by keyword must update. See backward compatibility concern in [Implementation Concerns §6](#6-backward-compatibility). Since the primary callers are LLMs reading the tool description fresh each session, the practical risk is low — but scripts and tests that reference `type_override` by name must be updated. |
| `title` | **Added** (new, optional) | Defaults to `None`. When provided, skips LLM extraction and files the document directly (UC3 mode switch). |
| `tags` | **Added** (new, optional) | Defaults to `None`. Comma-separated tags applied directly for document intake (UC3), or merged with LLM-generated tags for single-beat capture (UC2). |

The net effect is zero new tools. UC3 (document intake) is absorbed into `cb_file` via the `title` parameter acting as a mode switch.

## Net Tool Count

Before: 11 tools (cb_extract, cb_file, cb_recall, cb_read, cb_configure, cb_status, cb_setup, cb_enrich, cb_restructure, cb_review, cb_reindex).

Removed: 0.
Added: 0.

After: 11 tools. Net change: 0.

## Rationale

### Why not merge cb_extract and cb_file into one tool?

Considered and rejected. The inputs are fundamentally different: cb_extract takes a file path to a transcript; cb_file takes inline text content. Merging them would require a mode parameter or overloaded input semantics (is this a path or content?) that would make the tool harder for the LLM to use correctly. The security boundary on transcript_path (must be within `~/.claude/projects/`) is specific to session extraction and would be confusing when the tool is used for inline content.

### Why `title` as the mode switch instead of a `mode` parameter?

A `mode` parameter (e.g. `mode="extract"` vs `mode="direct"`) adds a knob the LLM has to get right. Using `title` as the mode switch is more natural: if the user says "file this report titled X", the LLM provides a title, which naturally triggers direct filing. If the user says "save this insight about Y", the LLM passes the description as content without a title, triggering extraction. The mode falls out of the natural parameter population rather than requiring explicit mode selection.

### Why not a separate `cb_import` or `cb_document` tool for UC3?

The tool count constraint prohibits adding a tool without removing one. More importantly, UC3 (document intake) shares the same write path as UC2 (single-beat capture): both route via write_beat/autofile_beat, both update the index, both write journal entries. The only difference is whether LLM extraction runs first. A separate tool would duplicate the entire write pipeline for a single behavioral difference that is cleanly expressed by the presence or absence of `title`.

### Why add `tags` as a parameter?

Document intake (UC3) needs a way to provide tags without LLM extraction. For single-beat capture (UC2), tags are optional and merged with LLM output. The parameter serves both modes without being required for either.

### Why not add more structure to UC3 (summary, relations, durability)?

YAGNI. The minimum viable document intake needs title, body, type, tags, and folder. Summary can be left blank (or auto-generated in a future enhancement). Relations are rarely specified manually. Durability defaults to "durable" (documents are inherently durable — if you're manually filing something, it's meant to last). If users need more fields, they can be added later without changing the interface shape.

## Implementation Concerns

### 1. Direct write path for document intake

When `title` is provided, cb_file must construct a beat dict and write it without calling `_extract_beats()`. This means building:
```python
beat = {
    "title": title,
    "type": type or "reference",
    "scope": "project" if cwd else "general",
    "summary": "",  # or first ~200 chars of content
    "tags": parse_tags(tags) if tags else [],
    "body": content,
    "durability": "durable",
    "relations": [],
}
```
This must go through the same `write_beat()` / `autofile_beat()` path as extracted beats. The `source` field should be `"document-intake"` to distinguish from `"manual-filing"` in the runs log.

### 2. Autofile behavior for document intake

When `folder` is omitted and autofile is enabled, document intake should use autofile to decide where to place the note. When `folder` is provided, it should skip autofile (same as current cb_file behavior). This is unchanged from current logic.

### 3. Search index update

`write_beat()` already calls `search_index.update_search_index()`. Document intake notes go through the same path, so index updates happen automatically. No special handling needed.

### 4. Summary generation

Extracted beats always have a summary (the LLM generates one). Document intake notes won't have one unless we auto-generate it. Options:
- Leave summary empty — the note is still searchable by title, tags, and body via FTS5.
- Generate summary from first ~200 chars of body — cheap, no LLM needed.

Recommend: generate from first sentence or first 200 chars, truncated at a sentence boundary. This is good enough for search result display without adding an LLM call.

### 5. Frontmatter for document intake

The `write_beat()` function in vault.py already generates frontmatter from a beat dict. Document intake beats go through the same function, so frontmatter generation is handled. The beat dict must include all fields that `write_beat()` expects (title, type, scope, summary, tags, body, durability, relations).

### 6. Backward compatibility

The `type_override` parameter rename to `type` is a breaking change for any client code that passes `type_override` by name. Since the MCP interface is used by LLMs (not programmatic clients), and the LLM reads the tool description fresh each session, this is low risk. However, if there are any scripts or tests that call `cb_file(type_override=...)`, they need updating.

### 7. Tag parsing

The `tags` parameter accepts a comma-separated string (e.g. `"python, async, concurrency"`). The implementation should strip whitespace and normalize: `[t.strip() for t in tags.split(",") if t.strip()]`. For UC2 mode, these tags should be merged with LLM-generated tags (union, no duplicates).

### 8. Title character validation

Document intake titles must go through `make_filename()` to strip `#`, `[`, `]`, `^` — same as extracted beat titles. The `write_beat()` function already does this, so no special handling is needed, but the implementation should be aware that user-provided titles may contain these characters.
