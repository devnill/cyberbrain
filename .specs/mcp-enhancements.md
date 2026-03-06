# Spec: MCP Enhancements — Discovery, Guidance, and Navigation

**Status:** Draft
**Date:** 2026-03-05
**Prereqs:** `cb_status` tool (implemented), FTS5 search backend (implemented)

---

## Motivation

The current MCP server has 4 tools and nothing else. MCP as a protocol has two additional
first-class mechanisms that help a client *discover* how to use a server:

- **Resources** — static or dynamic content the server advertises and the client can fetch.
  In Claude Desktop, resources are listed in the UI and can be embedded into conversations.
- **Prompts** — pre-composed message templates that appear as workflow entry points in
  Claude Desktop's UI (the `+` / slash-command menu). They guide the model through a
  multi-step interaction without the user knowing which tools to call.

Neither is implemented. As a result, Claude Desktop users get no behavioral guidance — the
model doesn't know when to call `cb_recall` proactively, when to file something, or that
the system even exists.

Beyond resources and prompts, two genuinely missing capabilities emerge from current usage:
the model can search notes but cannot navigate directly to one, and there is no way to ask
"what has been captured recently?" at session start.

This spec covers four features in order of impact:

1. **Resource: `cyberbrain://guide`** — behavioral guidance auto-available in Claude Desktop
2. **Prompts: `orient` and `recall`** — workflow entry points surfaced in Claude Desktop UI
3. **Tool: `cb_read`** — read a specific note by path or title
4. **Tool: `cb_recent`** — recently modified vault notes for session-start orientation

`cb_list`, `cb_edit`, and graph traversal are explicitly out of scope here.

---

## Part 1: Resource — `cyberbrain://guide`

### What MCP resources do

When an MCP server registers a resource, Claude Desktop lists it in the resource panel.
The model can reference it by URI. More importantly, prompts (Part 2) can fetch it and
inject its content into the conversation automatically.

### Content

The resource returns a markdown string: concise behavioral instructions for the model
explaining when and how to use each cyberbrain tool. This is the equivalent of a
system prompt for the server — it answers "how should I behave as an AI with access
to cyberbrain?".

**URI:** `cyberbrain://guide`
**MIME type:** `text/markdown`

**Content outline:**
```markdown
# Cyberbrain — AI Usage Guide

## What cyberbrain is
A personal knowledge vault for [user]'s Obsidian notes. Notes are extracted from
past Claude sessions and filed automatically. You have read and write access.

## When to call cb_recall
- At session start when the user mentions a project, technology, or topic they have
  worked on before. Call without asking permission; integrate results naturally.
- Mid-session when the conversation shifts to a new domain.
- When the user asks "what do I know about X?" or "have I done this before?".

## When to call cb_file
- When something durable is learned or decided during the session.
- When the user says "save this", "remember this", "file this", or similar.
- When you notice a non-obvious pattern worth preserving.

## When to call cb_recent
- At session start in a new conversation to orient on what has been recently captured.
- When the user asks "what have I been working on?" or "catch me up".

## When to call cb_extract
- Only when the user explicitly asks to process a transcript file.

## When to call cb_status
- When the user asks about system health, index stats, or recent extraction runs.

## Tool selection guide
| User intent | Tool |
|---|---|
| "Search my notes for X" | cb_recall |
| "Read the note about Y" | cb_read |
| "Save this" / "File this" | cb_file |
| "What have I been working on?" | cb_recent |
| "Process this transcript" | cb_extract |
| "Is everything healthy?" | cb_status |
```

### Implementation

```python
@mcp.resource("cyberbrain://guide")
def cyberbrain_guide() -> str:
    """Behavioral guidance for AI assistants using the cyberbrain knowledge vault."""
    return _GUIDE_TEXT  # module-level constant
```

FastMCP's `@mcp.resource(uri)` registers the resource in the server's capability
advertisement. No dynamic data needed — the guide is a static string.

**Note on automatic injection:** MCP resources are not automatically injected into
model context the way a system prompt is. The guide becomes useful when:
1. Referenced from a prompt (Part 2) so the model sees it on prompt invocation
2. Claude Desktop evolves to auto-include resources (the protocol supports this)
3. The user manually loads it via the resource panel

This is still worth implementing now: it has zero cost, establishes the pattern, and
the prompts make immediate use of it.

---

## Part 2: Prompts — `orient` and `recall`

### What MCP prompts do

Prompts appear in Claude Desktop's message composition UI (typically behind a `+` or
`/` prefix). When the user selects one, it composes a message and sends it — effectively
a one-click workflow trigger. The model receives the composed message and acts on it.

Prompts can include tool results and resource content via `EmbeddedResource` message parts.
They are the primary UX mechanism for guided workflows in Claude Desktop.

### Prompt: `orient`

**Purpose:** Session-start orientation. The user selects this at the start of a new
conversation to tell the model what cyberbrain is and what was recently captured.

**What it does:**
1. Fetches `cyberbrain://guide` resource content
2. Calls `cb_recent` (7 days, 10 results) and embeds output
3. Composes a message that places both in context

**Composed message:**
```
I'm starting a new session. Load the cyberbrain guide and show me what's been
recently captured so I can orient before we begin.

[embedded: cyberbrain://guide content]

Recent vault activity:
[embedded: cb_recent output]
```

The model sees the guide and recent notes simultaneously and can acknowledge them
naturally before the user asks their first real question.

**Implementation:**
```python
@mcp.prompt()
def orient() -> list[dict]:
    """
    Orient at session start: load the cyberbrain guide and surface recent vault activity.
    Select this prompt at the start of a new conversation.
    """
    config = _load_config()
    recent = cb_recent(days=7, max_results=10)
    guide = cyberbrain_guide()
    return [
        {
            "role": "user",
            "content": (
                "I'm starting a new session. Here is my knowledge vault guide and "
                "recent activity — use this to orient before we begin.\n\n"
                f"## Cyberbrain Guide\n\n{guide}\n\n"
                f"## Recent Vault Activity\n\n{recent}"
            ),
        }
    ]
```

### Prompt: `recall`

**Purpose:** Explicit search invocation. The user selects this when they want to search
their vault and get a synthesized answer, not just raw results.

**Parameters:** `query: str`

**What it does:** Composes a message that calls `cb_recall` with `synthesize=True` and
presents the result.

**Implementation:**
```python
@mcp.prompt()
def recall(query: str) -> list[dict]:
    """
    Search the knowledge vault and synthesize an answer. Provide a search query.
    """
    result = cb_recall(query=query, synthesize=True)
    return [
        {
            "role": "user",
            "content": f"Search my vault for: {query}\n\n{result}",
        }
    ]
```

### What to NOT add as a prompt

- A `file` prompt adds no value over just calling `cb_file` directly — filing is
  already well-described in the tool docstring and guide.
- A `status` prompt is redundant — `cb_status` is already a read-only idempotent tool
  that the model calls directly.

Two prompts is the right scope: `orient` (session start) and `recall` (explicit search).

---

## Part 3: Tool — `cb_read`

### Problem

`cb_recall` returns full body only for the top-2 results. If the model finds a relevant
note at position 4-5, or the user asks "read my note on X", there is no way to retrieve
it. The model is search-only with no deliberate navigation layer.

### Design

```python
@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True))
def cb_read(
    identifier: Annotated[str, Field(
        description=(
            "The note to read. Accepts: (1) a vault-relative path like "
            "'Projects/cyberbrain/JWT Auth Flow.md', (2) a note title like "
            "'JWT Auth Flow', or (3) a path returned in cb_recall results."
        )
    )],
) -> str:
    """
    Read the full content of a specific vault note by path or title.

    Use this when you have a specific note in mind — from a cb_recall result, a
    Related link, or a title the user mentioned. For searching across the vault,
    use cb_recall instead.

    Returns the full note content including frontmatter. Raises ToolError if the
    note is not found.
    """
```

**Resolution logic (in order):**
1. If `identifier` starts with the vault path or is a relative path that resolves within
   the vault → read directly
2. Strip leading vault path prefix if present → treat as vault-relative path
3. Try `{vault_path}/{identifier}` exactly
4. Try `{vault_path}/{identifier}.md` (extension omitted)
5. Search FTS5 index for a title exact-match (case-insensitive): `SELECT path FROM notes WHERE title = ?`
6. Fall back to FTS5 title prefix search: `SELECT path FROM notes WHERE title LIKE ?`
7. If still not found → `ToolError("Note not found: {identifier}. Try cb_recall to search.")`

**Security:** Resolved path must be within `vault_path` (resolve + relative_to check).
Same pattern as `cb_extract`'s transcript path validation.

**Return format:**
```
# {title}

{full file content including frontmatter}

---
Source: {vault-relative path}
```

---

## Part 4: Tool — `cb_recent`

### Problem

`cb_status` shows what extraction runs happened (pipeline-centric). There is no way to
ask "what notes are in my vault from the last week?" — a note-centric, session-start
oriented query that's one of the most natural things to want at the start of a session.
This is also distinct from `cb_recall` which requires a specific query.

### Design

```python
@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True))
def cb_recent(
    days: Annotated[int, Field(ge=1, le=90, description="How many days back to look")] = 7,
    max_results: Annotated[int, Field(ge=1, le=50)] = 10,
    note_type: Annotated[str | None, Field(
        description="Filter by note type, e.g. 'decision', 'insight', 'problem', 'reference'. Omit for all types."
    )] = None,
    project: Annotated[str | None, Field(
        description="Filter to a vault-relative folder prefix, e.g. 'Projects/cyberbrain'. Omit for all folders."
    )] = None,
) -> str:
    """
    Show vault notes modified in the last N days, sorted most-recent first.

    Use this at session start to orient on what has been recently captured, or when
    the user asks "what have I been working on?" or "catch me up on recent notes."
    For searching notes by topic, use cb_recall. For extraction run history, use cb_status.

    Returns note cards with title, type, tags, summary, and vault path.
    Returns "No recent notes found" if nothing was modified in the requested window.
    """
```

**Implementation:**
- Walk vault markdown files (or query SQLite `notes` table if available — mtime not
  stored there, so filesystem walk is simpler)
- Filter by `mtime >= now - timedelta(days=days)`
- Filter by `note_type` if provided (read frontmatter type field)
- Filter by path prefix if `project` provided
- Sort by mtime descending, take top `max_results`
- Return note cards: title, type, date, summary, tags, vault-relative path

**No LLM call.** Pure filesystem + frontmatter read. Fast.

**Return format:**
```
Recent vault notes (last {days} days) — {N} result(s)

### {title} (type: {type}, modified: {date})
{summary}
Tags: {tags}
Source: {vault-relative path}

---
```

---

## Implementation Order

| Step | Feature | Effort | Notes |
|------|---------|--------|-------|
| 1 | `cb_recent` tool | 1h | No deps; needed by `orient` prompt |
| 2 | `cb_read` tool | 1h | Path resolution + FTS5 title lookup |
| 3 | `cyberbrain://guide` resource | 30m | Static string; write the content carefully |
| 4 | `orient` prompt | 30m | Depends on cb_recent and the resource |
| 5 | `recall` prompt | 15m | Thin wrapper; depends on cb_recall |

Total: ~4 hours. All changes are additive to `mcp/server.py` — no changes to
extractors, hooks, or skills.

---

## What is NOT in this spec

| Feature | Why excluded |
|---------|-------------|
| `cb_list` (browse folder) | Search + cb_read covers the use case without a new command |
| `cb_edit` (append/edit notes) | Write capability — separate concern, separate spec |
| `cb_recall` filter params (type, since, tags) | Valid enhancement but independent of discovery; address in a search-quality spec |
| Knowledge graph / relations | High effort, architectural change — deferred |
| `cb_extract` prompt | Low value; transcript processing is not a natural Claude Desktop workflow |

---

## FastMCP Reference

```python
# Resource
@mcp.resource("cyberbrain://guide")
def my_resource() -> str: ...

# Prompt
@mcp.prompt()
def my_prompt(query: str) -> list[dict]:
    return [{"role": "user", "content": "..."}]

# Tool (existing pattern)
@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def my_tool(...) -> str: ...
```

Prompts with arguments appear in Claude Desktop with an input form before sending.
Prompts without arguments send immediately on selection.
