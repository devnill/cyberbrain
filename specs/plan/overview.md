# Cyberbrain

## What We Are Building
Cyberbrain is a knowledge capture and retrieval system for LLM interactions. It automatically extracts durable knowledge ("beats") from Claude sessions and stores them as structured Obsidian markdown notes, making that knowledge searchable and injectable into future sessions.

The system operates in three layers: **capture** (hooks that fire on compaction and session end, calling an LLM to extract structured beats from transcripts), **storage** (an Obsidian vault with typed, tagged, routed markdown notes and optional search indexes), and **retrieval** (MCP tools that search, read, synthesize, and inject vault content into active sessions).

Beyond basic capture and retrieval, the system provides a full curation pipeline: autofile routing to vault folders, batch frontmatter enrichment, working memory lifecycle management (promote/extend/delete ephemeral notes), and vault restructuring (merge related notes, split large ones, create hub pages, organize into subfolders). The MCP server exposes 11 tools and is compatible with Claude Desktop, Claude Code, Cursor, and other MCP clients.

## Key Components

- **Extractors** — Core engine: transcript parsing, LLM-driven beat extraction, beat validation, frontmatter helpers
- **Vault I/O** — Note writing, filename sanitization, scope-based routing, relation resolution, autofile (LLM-driven folder selection), run log and dedup, vault structure analysis
- **Search** — Three-tier search: grep fallback, FTS5 full-text, hybrid (FTS5 + embedding vectors via usearch + RRF fusion). Index lifecycle management.
- **MCP Server** — FastMCP v3 server with 11 tools: cb_extract, cb_file, cb_recall, cb_read, cb_setup, cb_enrich, cb_configure, cb_status, cb_restructure, cb_review, cb_reindex
- **LLM Backends** — Three backends: claude-code (subprocess to `claude -p`), bedrock (Anthropic SDK + AWS), ollama (local inference)
- **Hooks** — PreCompact and SessionEnd bash hooks for automatic capture
- **Prompts** — 19 LLM prompt templates across 5 families (extraction, autofile, enrichment, restructure, review)
- **Config** — Two-level configuration (global + per-project) plus vault CLAUDE.md as source of truth
- **Import** — Batch import for Claude Desktop and ChatGPT data exports

## Project Structure

```
cyberbrain/
├── extractors/          # Core engine (~2,800 LOC)
├── mcp/                 # MCP server and tools (~4,400 LOC)
│   ├── server.py        # FastMCP entry point
│   ├── shared.py        # Bridge to extractors
│   ├── resources.py     # MCP resources and prompts
│   └── tools/           # 10 tool implementations
├── hooks/               # Bash hooks for capture
├── prompts/             # 19 LLM prompt templates
├── scripts/             # Import utilities
├── tests/               # Test suite (~17,600 LOC)
├── specs/               # Planning artifacts (this directory)
│   ├── legacy/          # Original specs (v1_spec, GOALS, deferred, etc.)
│   ├── steering/        # Guiding principles, constraints, interview
│   └── plan/            # Architecture, modules, work items
├── build.sh / install.sh / uninstall.sh
└── CLAUDE.md            # Project documentation
```

## Workflow

**Automatic capture:** User works in Claude Code normally. On compaction, PreCompact hook fires → extracts beats from transcript via LLM → writes typed markdown notes to vault → updates search index. On session end without compaction, SessionEnd hook does the same.

**Manual capture:** User calls `cb_file` via MCP with text to capture → LLM classifies into beats → routes and writes to vault.

**Retrieval:** User (or proactive recall) calls `cb_recall` with a query → hybrid search finds relevant notes → optionally synthesizes results via LLM → injects into session context. `cb_read` retrieves a specific note by path or title.

**Curation:** `cb_enrich` adds/corrects frontmatter metadata in batch. `cb_restructure` merges related notes, splits large ones, creates hub pages, organizes folders. `cb_review` manages working memory lifecycle (promote durable notes, extend useful ephemeral ones, delete stale ones).

## Active Workstreams

1. **Vault curation quality** — Improve the full curation pipeline (extraction, autofile, enrichment, restructure, working memory). Restructuring is the hardest problem: false groupings, multi-pass requirements, model capability gaps. Cross-cutting: build evaluation tooling for comparing output quality across alternative approaches.

2. **RAG and retrieval** — Build production-quality RAG with synthesis, context injection, and automatic invocation across all interfaces. Research ML approaches (graph + embeddings) for higher-quality semantic search. Validate automatic invocation in Claude Desktop before further development.
