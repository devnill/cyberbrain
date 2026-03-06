# MCP Gap Analysis: Cyberbrain vs. basic-memory

**Date:** 2026-03-03
**Reference:** https://github.com/basicmachines-co/basic-memory
**Context:** Deep comparison of MCP server capabilities to identify enhancement opportunities for cyberbrain.

---

## Current State

### Cyberbrain MCP: 3 tools, 0 resources, 0 prompts

| Tool | What it does |
|------|-------------|
| `cb_extract` | Extract beats from a transcript path, write to vault |
| `cb_file` | Classify provided text as beats, write to vault |
| `cb_recall` | Grep-based keyword search, returns top-N notes |

### basic-memory MCP: 18 tools, 2 resources, 4 prompts

| Tool | Purpose |
|------|---------|
| `write_note` | Create or update Markdown entities |
| `edit_note` | Incremental edits: append, prepend, find_replace, replace_section |
| `read_note` | Retrieve note by title, permalink, or memory:// URL |
| `view_note` | Render note as formatted artifact |
| `delete_note` | Remove note or directory |
| `move_note` | Relocate with DB consistency |
| `read_content` | Raw file content (text, images, binaries) |
| `search_notes` | FTS5/vector/hybrid search with filters |
| `build_context` | Recursive graph traversal from memory:// URL |
| `recent_activity` | Recently modified content; cross-project mode |
| `list_directory` | Browse folder structure with glob filtering |
| `list_memory_projects` | All projects with stats |
| `create_memory_project` | Initialize new project |
| `delete_project` | Remove project from config |
| `sync_status` | Check file-database sync state |
| `canvas` | Generate Obsidian canvas visualizations |
| `schema_validate` / `schema_infer` / `schema_diff` | Schema tooling |
| `cloud_info`, `release_notes` | Operational info |

Resources: `memory://ai_assistant_guide`, `memory://project_info/{project}`
Prompts: `continue_conversation`, `recent_activity`, `search_knowledge_base`, `ai_assistant_guide`

---

## Gap 1: No Vault Read

**Missing tool:** `read_note` equivalent

`cb_recall` returns summaries and full bodies for the top 2 search results, but the AI can't navigate to a specific note by path or title and read it deliberately. If a search surfaces 5 results and the AI wants to inspect result #4 fully, there's no tool for that.

**Impact:** High. The AI can find notes but can't navigate them — search-only with no read layer.

**Opportunity:** Add `cb_read(identifier)` — accepts a vault-relative path, title, or slug — returns full note content with frontmatter. Straightforward vault file read.

---

## Gap 2: Search Quality

**Affected tool:** `cb_recall`

`cb_recall` uses `grep -r -l` per term, ranks by `(match_count, mtime)`. No relevance scoring, no phrase matching, no filters, no FTS5.

basic-memory: FTS5 with boolean operators, phrase queries, optional vector/hybrid search, filters by type/tag/date/metadata, AND→OR fallback relaxation.

**Specific deficiencies:**

- No phrase matching (can't search for exact multi-word expressions)
- No date filtering ("notes from last week")
- No type filtering ("find all `decision` beats about authentication")
- No tag filtering
- No relevance score — ranking by match count + mtime is crude
- No cross-field weighting (title match should rank higher than body match)

**Impact:** High. Poor recall quality undermines the core value proposition.

**Opportunity (option A — heavier):** Replace grep with SQLite FTS5. Build a lightweight index alongside the vault on first run, rebuild incrementally. Self-contained, no new dependencies beyond `sqlite3` (stdlib). Adds phrase queries, relevance scoring, and filter predicates as parameters to `cb_recall`.

**Opportunity (option B — lighter):** Keep grep as the engine but add `--type`, `--tag`, `--since`, `--scope` parameters that post-filter the result set. Add a configurable scoring function that weights title matches higher.

---

## Gap 3: No Recent Activity

**Missing tool:** `recent_activity` equivalent

basic-memory's `recent_activity` is a distinct use case from search: "what did I capture recently?" / "pick up where I left off." cyberbrain has no equivalent. The AI can't orient itself at session start by asking what was recently filed.

**Impact:** Medium-high. One of the most natural session-start behaviors; basic-memory treats it as a first-class workflow.

**Opportunity:** Add `cb_recent(days=7, max_results=10, type=None, project=None)` — reads `mtime` on all vault markdown files in configured inbox/project folder(s), sorts descending, optionally filters by frontmatter type, returns the result set. No index required — pure filesystem mtime scan. Could also surface recent sessions from `cb-extract.log` (session-level recency: what sessions were extracted in the last N days).

---

## Gap 4: No Vault Browse / List

**Missing tool:** `list_directory` equivalent

The AI can't inspect vault structure — what folders exist, what notes are in a project's folder, what the filing hierarchy looks like. Search-only with no browse layer.

**Impact:** Medium.

**Opportunity:** Add `cb_list(folder=None, depth=1)` — returns the vault folder/file tree under the given path (relative to vault root), with note titles and types from frontmatter. Pairs naturally with `cb_read` for browse-then-read workflows.

---

## Gap 5: No Append / Edit Existing Notes

**Missing tool:** `edit_note` equivalent

cyberbrain can create new beats but can't edit existing vault notes via MCP. The autofile `extend` action appends to existing notes during extraction, but that's internal — the AI can't say "append this to my existing Python patterns note."

basic-memory has `edit_note` with `append`, `prepend`, `find_replace`, `replace_section` operations.

**Impact:** Medium. Limits the AI to inbox accumulation — it can't curate or update notes.

**Opportunity:** Add `cb_edit(identifier, operation, content, section=None)` supporting at minimum `append`. Validate path stays within vault before writing. Reuse the existing `make_filename()` path validation logic.

---

## Gap 6: No MCP Resource for Guidance

**Missing:** MCP Resource

basic-memory registers `memory://ai_assistant_guide` as an MCP Resource. Claude Desktop auto-fetches resources and injects them into context — usage instructions are always present without user action.

cyberbrain registers no MCP resources. The AI using cyberbrain via Claude Desktop receives no behavioral guidance — it doesn't know when to call `cb_recall` at session start, when to call `cb_file` for important insights, or how the system works.

**Impact:** Medium. Significantly reduces Claude Desktop integration effectiveness.

**Opportunity:** Register a `memory://cyberbrain_guide` MCP Resource returning usage guidance: call `cb_recall` at session start when working in a known project domain, call `cb_file` when something durable is learned, call `cb_recent` to orient at session start. Minimal to implement with FastMCP — one `@mcp.resource()` decorated function returning a markdown string.

---

## Gap 7: No MCP Prompts

**Missing:** MCP Prompts

basic-memory registers 4 MCP prompts — `continue_conversation`, `recent_activity`, `search_knowledge_base`, `ai_assistant_guide`. Prompts appear as slash-command-style entry points in Claude Desktop's UI. They wrap tool calls with contextual formatting and next-step suggestions.

cyberbrain's 5 skills (`/cb-recall`, `/cb-file`, etc.) are Claude Code CLI-only and don't surface in Claude Desktop.

**Impact:** Medium. Claude Desktop users get no natural-language entry points for common workflows.

**Opportunity:** Register MCP prompts for the primary workflows: a `recall` prompt (equivalent to `/cb-recall`), a `file` prompt, and a `recent` prompt. These wrap tool calls with guidance text and require no new backend logic.

---

## Gap 8: No Related Note Links

**Partially present, not exposed**

When `autofile_beat()` runs, it calls `search_vault()` to find related notes — but only for routing decisions. That related-note signal is discarded after routing. The written beat has an empty `related: []` frontmatter field that's never populated.

basic-memory writes `- relation_type [[Target Entity]]` syntax that becomes a graph edge in SQLite.

**Impact:** Medium. Notes are semantically isolated. The AI can't follow "related to" chains.

**Opportunity (light):** After routing, populate `related:` frontmatter in the written beat with wikilinks to the top-N related notes found by `search_vault()`. No schema change, no DB required — just write `[[Note Title]]` entries. This makes notes graph-connected in Obsidian's graph view without a separate index.

**Opportunity (heavy):** Introduce an SQLite index with Observations and Relations tables, plus a `build_context`-style traversal tool. Significant architectural change — deferred.

---

## Gap 9: No Vault Stats

**Missing:** `project_info` / stats endpoint

basic-memory exposes entity/observation/relation counts, graph metrics, and system status via the `project_info` MCP Resource. cyberbrain has no equivalent.

**Impact:** Low for v1.

---

## Prioritized Opportunities

| Priority | Gap | Effort | Impact | Feature |
|----------|-----|--------|--------|---------|
| 1 | Search quality | Medium | High | Upgrade `cb_recall` with FTS5 index or add filter params |
| 2 | Read notes | Low | High | Add `cb_read(identifier)` tool |
| 3 | Recent activity | Low | High | Add `cb_recent(days, type, project)` tool |
| 4 | MCP Resource (guide) | Low | Medium | Register `memory://cyberbrain_guide` resource |
| 5 | MCP Prompts | Low | Medium | Register `recall`, `file`, `recent` prompts |
| 6 | Browse vault | Low | Medium | Add `cb_list(folder, depth)` tool |
| 7 | Append/edit notes | Medium | Medium | Add `cb_edit(identifier, operation, content)` tool |
| 8 | Related note links | Medium | Medium | Populate `related:` frontmatter from `search_vault()` output |
| 9 | Knowledge graph | High | High (long-term) | SQLite Relations table + graph traversal tool |

---

## What Cyberbrain Has That basic-memory Doesn't (Don't Lose)

- **Passive PreCompact extraction** — the core differentiator; nothing in basic-memory does this
- **Retroactive transcript mining** — can extract from past sessions
- **SessionEnd hook** — captures sessions that close without compaction
- **Vault-adaptive ontology** — reads vault CLAUDE.md; no hardcoded type vocabulary
- **Dry-run mode** — first-class preview across all operations
- **No daemon** — no always-running process; simpler operational model
- **LLM extraction quality** — dedicated extraction pass against full transcript; surfaces beats the user didn't think to note

---

## Reference: basic-memory MCP Tool Details

### `build_context` — Graph Traversal

Takes a `memory://` URL, walks `Relation` edges via recursive CTE SQL to configurable depth, bidirectionally. Returns primary results + related entities with observations.

`GraphContext` schema:
```
results: list[ContextResult]
  └── primary_result: EntitySummary
  └── observations: list[ObservationSummary]
  └── related_results: list[EntitySummary | RelationSummary]
metadata: MemoryMetadata (uri, primary_count, related_count, depth, timeframe, page)
```

### `search_notes` — FTS5 + Filters

Parameters: `query`, `search_type` (fts/semantic/hybrid/title/permalink), `types`, `tags_filter`, `after_date`, `before_date`, `metadata_filter`, `page`, `page_size`.

Fallback: strict AND → relaxed OR (skipped for explicit boolean queries, short queries, phrase queries).

### `edit_note` — Operations

`append`, `prepend` — auto-creates note if not found.
`find_replace`, `replace_section` — require existing note.

### `memory://` URL Scheme

| Format | Example |
|--------|---------|
| Bare path | `specs/search` |
| Prefixed | `memory://specs/search` |
| Wildcard | `memory://folder/*` |
| Project-prefixed | `memory://my-project/specs/search` |

Forbidden characters in path: `<`, `>`, `"`, `|`, `?`
