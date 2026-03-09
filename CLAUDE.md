# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Specification

The authoritative requirements document for this project is:

| Document | Purpose |
|---|---|
| [`.specs/v1_spec.md`](.specs/v1_spec.md) | V1 specification — UX requirements, feature scope, architecture decisions, success criteria |

Read `.specs/v1_spec.md` before making any significant changes. It supersedes all prior steering documents and phase specs.

---

## Project Overview

A knowledge capture and retrieval system for LLM interactions. It automatically extracts durable knowledge ("beats") from Claude sessions and stores them as structured Obsidian markdown notes, making that knowledge searchable and injectable into future sessions.

The system exposes an MCP server with ten tools (`cb_extract`, `cb_file`, `cb_recall`, `cb_read`, `cb_setup`, `cb_enrich`, `cb_configure`, `cb_status`, `cb_restructure`, `cb_review`, `cb_reindex`), a PreCompact hook for automatic capture, and CLI import scripts for Claude and ChatGPT data exports. The MCP server is the single interface — no slash command skills.

---

## Build & Install

```bash
bash build.sh          # build release tarball
bash build.sh --clean  # wipe dist/ before building
bash install.sh        # install to ~/.claude/
bash uninstall.sh [--yes]  # uninstall
```

**Validate the extractor directly:**
```bash
python3 extractors/extract_beats.py \
  --transcript <path-to-jsonl> \
  --session-id test-session \
  --trigger manual \
  --cwd /some/project/path
```

Pass `--beats-json <path>` instead of `--transcript` to skip transcript parsing and feed pre-extracted beats JSON directly.

**Test the hook independently:**
```bash
echo '{"transcript_path": "/path/to/transcript.jsonl", "session_id": "test-123", "trigger": "compact", "cwd": "/Users/dan/code/my-project"}' | \
  bash hooks/pre-compact-extract.sh
```

**Run the test suite:**
```bash
python3 -m pytest tests/
```

**Hot reload:** The hook and `extract_beats.py` reload on each invocation. MCP server changes require restarting Claude Desktop.

---

## Architecture

### Data Flow

```
Claude Code session
  → PreCompact event fires hooks/pre-compact-extract.sh
  → invokes extractors/extract_beats.py with transcript path
  → calls LLM (via configured backend) to extract beats as JSON
  → writes .md files to Obsidian vault
```

Beat routing:
- `scope: project` → project vault folder (from `.claude/cyberbrain.local.json`)
- `scope: general` → `inbox` folder (warn and skip if inbox is not configured)
- `durability: working-memory` → working memory folder (`AI/Working Memory/<project>/` or `AI/Working Memory/`) regardless of scope

### Key Files

| File | Purpose |
|---|---|
| `hooks/pre-compact-extract.sh` | PreCompact hook; reads hook context JSON from stdin, strips nested-session env vars, calls extractor; always exits 0 |
| `extractors/extract_beats.py` | Core engine; parses JSONL/text transcripts, calls LLM backend, writes vault notes, daily journal |
| `extractors/backends.py` | LLM backend implementations (claude-code, bedrock, ollama); env var stripping; subprocess hardening |
| `extractors/analyze_vault.py` | Vault structure analyzer used by `cb_setup`; produces JSON report |
| `prompts/extract-beats-system.md` / `extract-beats-user.md` | Extraction LLM prompts — edit to change extraction behavior |
| `prompts/autofile-system.md` / `autofile-user.md` | Autofile routing prompts |
| `prompts/enrich-system.md` / `enrich-user.md` | Batch enrichment prompts — support `{vault_type_context}` injection |
| `mcp/server.py` | FastMCP v3 server for Claude Desktop; registers all tools; runs in `~/.claude/cyberbrain/venv/` |
| `mcp/tools/extract.py` | `cb_extract` tool |
| `mcp/tools/file.py` | `cb_file` tool |
| `mcp/tools/recall.py` | `cb_recall` + `cb_read` tools |
| `mcp/tools/setup.py` | `cb_setup` tool — two-phase vault analysis and CLAUDE.md generation |
| `mcp/tools/enrich.py` | `cb_enrich` tool — batch frontmatter enrichment |
| `mcp/tools/manage.py` | `cb_configure` + `cb_status` tools |
| `mcp/tools/restructure.py` | `cb_restructure` tool — split large notes, merge related clusters, create hub pages, and move clusters into subfolders |
| `mcp/tools/review.py` | `cb_review` tool — working memory review (promote/extend/delete) |
| `prompts/restructure-system.md` / `restructure-user.md` | Restructure LLM prompts (split + merge) |
| `prompts/restructure-decide-system.md` / `restructure-decide-user.md` | Restructure decision prompts — action selection for clusters and large notes |
| `prompts/restructure-generate-system.md` / `restructure-generate-user.md` | Restructure content generation prompts |
| `prompts/restructure-audit-system.md` / `restructure-audit-user.md` | Restructure audit prompts — topical fit and quality checks |
| `prompts/restructure-group-system.md` / `restructure-group-user.md` | Restructure grouping prompts — LLM-driven semantic clustering |
| `mcp/tools/reindex.py` | `cb_reindex` tool — prune stale index entries or full rebuild |
| `prompts/review-system.md` / `review-user.md` | Working memory review LLM prompts |
| `scripts/import.py` | Unified import for Claude Desktop and ChatGPT data exports |
| `tests/` | Test suite — unit and integration tests with mocked LLM calls |

### Beat Types

The extractor uses 4 types (defined by the vault's CLAUDE.md; these are the defaults):

| Type | What it captures |
|---|---|
| `decision` | A choice made between alternatives, with rationale |
| `insight` | A non-obvious understanding or pattern discovered |
| `problem` | Something broken, blocked, or constrained — with or without resolution |
| `reference` | A fact, command, snippet, or configuration detail for future lookup |

Each beat also carries a **durability** field:
- `"durable"` — passes the six-month test: useful to someone with no memory of this session six months from now
- `"working-memory"` — current project state that matters now but is unlikely to matter long-term (open bugs, in-flight refactors, temporary workarounds, unvalidated hypotheses)

### Configuration

Global config at `~/.claude/cyberbrain/config.json`:
```json
{
  "vault_path": "/path/to/vault",
  "inbox": "AI/Claude-Sessions",
  "backend": "claude-code",
  "model": "claude-haiku-4-5",
  "claude_timeout": 120,
  "autofile": false,
  "daily_journal": false,
  "journal_folder": "AI/Journal",
  "journal_name": "%Y-%m-%d",
  "proactive_recall": true,
  "working_memory_folder": "AI/Working Memory",
  "working_memory_review_days": 28,
  "consolidation_log": "AI/Cyberbrain-Log.md",
  "consolidation_log_enabled": true,
  "trash_folder": ".trash"
}
```

The vault's `CLAUDE.md` may contain a `## Cyberbrain Preferences` section (managed via `cb_configure(show_prefs/set_prefs/reset_prefs)`) that is injected into extraction and restructure prompts to guide LLM behavior without editing prompt files directly.

Per-project config at `.claude/cyberbrain.local.json` (searched up the directory tree from the session's cwd):
```json
{
  "project_name": "my-project",
  "vault_folder": "Projects/my-project/Claude-Notes"
}
```

### LLM Backends

Three backends, selected via `backend` config key:

| Backend | Key | Auth | Notes |
|---|---|---|---|
| `claude-code` | `model` | None (uses active session) | Default; shells out to `claude -p` |
| `bedrock` | `model` | AWS credentials | Anthropic SDK + Bedrock |
| `ollama` | `model`, `ollama_url` | None | Local inference; default URL `http://localhost:11434` |

### Claude Code Environment Variables

When `claude -p` is spawned as a subprocess, these inherited env vars cause hangs and must be stripped before the subprocess launches:

- `CLAUDECODE`
- `CLAUDE_CODE_ENTRYPOINT`
- `CLAUDE_CODE_DISABLE_FEEDBACK_SURVEY`
- `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`

The `claude-code` backend strips all four unconditionally and uses `start_new_session=True` to fully detach from the parent process group. The subprocess also runs from a neutral working directory (`~/.claude/cyberbrain/`) that has no CLAUDE.md, preventing project config injection.

**Architectural constraint:** All vault writes go through `extract_beats.py` or `import.py`. This ensures path validation, logging, and error fallback are consistently enforced in Python. MCP tools never write vault files directly.

**Filename character constraint:** Beat titles (used as vault filenames) must not contain `#`, `[`, `]`, or `^`. These characters are valid on the filesystem but break Obsidian wikilink resolution — Obsidian uses `#` as a heading anchor separator and `^` as a block reference marker inside link syntax. The `make_filename()` function in `extract_beats.py` strips them, and the extraction and autofile prompts instruct the LLM not to generate them. When writing prompts or testing, verify titles avoid these characters (e.g. use "CSharp" not "C#").

**Soft delete (trash):** All vault note deletions go through `_move_to_trash()` in `mcp/shared.py`. Notes are moved to the `trash_folder` (default `.trash`, relative to vault root) instead of being permanently deleted. The vault-relative folder structure is preserved inside the trash folder. If a file already exists at the destination, a numeric suffix (`_1`, `_2`, ...) is appended to avoid clobbering. Obsidian ignores dotfolders by default, so `.trash` is invisible in the vault UI.

**Restructure grouping strategies:** `cb_restructure` in `folder_hub` mode supports pluggable clustering via the `grouping` parameter:
- `auto` (default) — embedding hierarchical clustering with LLM fallback if no embeddings available
- `embedding` — deterministic agglomerative clustering from usearch embeddings (cosine distance, average linkage, threshold 0.25)
- `llm` — LLM-driven semantic grouping using the `restructure-group-system.md` prompt
- `hybrid` — embedding pre-clustering then LLM validation/refinement using the full group prompt

Grouping results are cached at `~/.claude/cyberbrain/.restructure-groups-cache.json` so that dry_run → preview → execute use the same clusters. The cache is keyed by folder path, note count, and strategy.

**Restructure execution order:** Audit runs before structural decisions. Notes flagged as `flag-misplaced` or `flag-low-quality` are removed from clusters before the decide/generate/execute phases, preventing merges of notes that should be moved or deleted.

### MCP Interface

The MCP server (`mcp/`) is the single interface for both Claude Desktop and Claude Code. It runs as a separate process (stdio transport) — architecturally isolated from the user's main Claude session. All LLM inference for extraction, enrichment, and setup happens in `claude -p` subprocess calls spawned from the MCP server process, not from the user's session.

```
Claude Code / Claude Desktop (process A — user session, expensive model)
  └── MCP server (process B — launched at startup, stdio transport)
        └── claude -p (process C — spawned per extraction, cheap model)
```

---

## Distribution

The release tarball includes hooks, extractors, prompts, and the MCP server. `install.sh` copies files to `~/.claude/` and registers the PreCompact hook in `~/.claude/settings.json`.
