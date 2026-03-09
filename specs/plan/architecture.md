# Architecture: Cyberbrain

## System Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                        USER INTERFACES                               │
│                                                                      │
│  Claude Code (session)        Claude Desktop        CLI Scripts      │
│       │                            │                     │           │
│       ▼                            │                     │           │
│  ┌─────────────┐                   │                     │           │
│  │ PreCompact  │                   │                     │           │
│  │ SessionEnd  │                   │                     │           │
│  │   hooks/    │                   │                     │           │
│  └──────┬──────┘                   │                     │           │
│         │                          ▼                     │           │
│         │              ┌──────────────────┐              │           │
│         │              │   MCP Server     │              │           │
│         │              │   (stdio, FastMCP)│             │           │
│         │              │                  │              │           │
│         │              │  10 tools        │              │           │
│         │              │  1 resource      │              │           │
│         │              │  2 prompts       │              │           │
│         │              └────────┬─────────┘              │           │
│         │                       │                        │           │
└─────────┼───────────────────────┼────────────────────────┼───────────┘
          │                       │                        │
          ▼                       ▼                        ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     EXTRACTOR LAYER (Python)                         │
│                                                                      │
│  ┌─────────┐  ┌───────────┐  ┌─────────┐  ┌──────────┐             │
│  │extract  │  │ autofile  │  │  vault   │  │ config   │             │
│  │_beats   │  │           │  │          │  │          │             │
│  │(entry)  │  │           │  │          │  │          │             │
│  └────┬────┘  └─────┬─────┘  └────┬─────┘  └──────────┘             │
│       │             │             │                                   │
│  ┌────▼────┐  ┌─────▼─────┐  ┌───▼────┐  ┌────────────┐            │
│  │extractor│  │ frontmatter│  │run_log │  │analyze_vault│            │
│  └────┬────┘  └───────────┘  └────────┘  └────────────┘            │
│       │                                                              │
│  ┌────▼────┐                  ┌────────────────────────┐            │
│  │backends │                  │   search layer          │            │
│  │         │                  │  ┌────────────────────┐ │            │
│  │ claude  │                  │  │ search_backends.py │ │            │
│  │ bedrock │                  │  │  grep / fts5 /     │ │            │
│  │ ollama  │                  │  │  hybrid (usearch)  │ │            │
│  └─────────┘                  │  └────────────────────┘ │            │
│                               │  ┌────────────────────┐ │            │
│                               │  │ search_index.py    │ │            │
│                               │  │  coordination      │ │            │
│                               │  └────────────────────┘ │            │
│                               └────────────────────────┘            │
└──────────────────────────────────────────────────────────────────────┘
          │                       │                        │
          ▼                       ▼                        ▼
┌──────────────────────────────────────────────────────────────────────┐
│                        STORAGE                                       │
│                                                                      │
│  Obsidian Vault (markdown)    SQLite search-index.db    Config JSON  │
│  ~/vault/                     ~/.claude/cyberbrain/     ~/.claude/   │
│   ├── CLAUDE.md                search-index.db          cyberbrain/  │
│   ├── AI/Claude-Sessions/      search-index.usearch     config.json  │
│   ├── AI/Working Memory/       search-index-manifest    .claude/     │
│   ├── AI/Journal/                                       cyberbrain   │
│   └── Projects/...            Logs                      .local.json  │
│                               ~/.claude/cyberbrain/                  │
│                                logs/cb-extract.log                   │
│                                logs/cb-runs.jsonl                    │
│                                wm-recall.jsonl                       │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Component Map

| Component | Files | Responsibility |
|-----------|-------|----------------|
| **Hooks** | `hooks/pre-compact-extract.sh`, `hooks/session-end-extract.sh`, `hooks/hooks.json` | Lifecycle event handlers that trigger automatic extraction |
| **Extractor entry** | `extractors/extract_beats.py` | CLI entry point; re-exports all extractor submodules; orchestrates extraction pipeline |
| **LLM extraction** | `extractors/extractor.py` | Calls LLM backend with transcript + prompts; parses JSON response |
| **Backends** | `extractors/backends.py` | Three LLM backend implementations (claude-code, bedrock, ollama) |
| **Transcript parsing** | `extractors/transcript.py` | Parses JSONL transcripts into plain-text conversation format |
| **Vault I/O** | `extractors/vault.py` | Beat writing, output routing, relation resolution, filename generation, type validation |
| **Autofile** | `extractors/autofile.py` | LLM-driven filing decisions (create vs extend); collision handling |
| **Frontmatter** | `extractors/frontmatter.py` | Canonical YAML frontmatter parsing and normalisation |
| **Config** | `extractors/config.py` | Two-level config loading (global + project); prompt file loading |
| **Run log** | `extractors/run_log.py` | Deduplication log, structured runs log, daily journal writing |
| **Vault analyzer** | `extractors/analyze_vault.py` | Vault structure analysis for cb_setup (directories, frontmatter, tags, wikilinks) |
| **Search backends** | `extractors/search_backends.py` | Pluggable search: GrepBackend, FTS5Backend, HybridBackend; RRF fusion |
| **Search index** | `extractors/search_index.py` | Coordination layer: incremental updates, full rebuild, backend lifecycle |
| **MCP server** | `mcp/server.py` | FastMCP entry point; imports and registers all tool/resource modules |
| **MCP shared** | `mcp/shared.py` | Bridge between MCP tools and extractor layer; config helpers; trash/index helpers |
| **MCP resources** | `mcp/resources.py` | `cyberbrain://guide` resource; `orient` and `recall` prompts |
| **MCP tools** | `mcp/tools/{extract,file,recall,manage,setup,enrich,restructure,review,reindex}.py` | 10 MCP tools |
| **Prompts** | `prompts/*.md` (19 files) | LLM prompt templates for extraction, autofile, enrichment, restructure, review |
| **Import script** | `scripts/import.py` | Batch import of Claude Desktop and ChatGPT data exports |

---

## Data Flow

### 1. Capture Pipeline (automatic)

```
Claude Code session
  → PreCompact event fires
  → hooks/pre-compact-extract.sh reads hook context JSON from stdin
  → Invokes extractors/extract_beats.py with --transcript, --session-id, --trigger, --cwd
  → config.py loads global + project config
  → transcript.py parses JSONL to plain text
  → extractor.py reads vault CLAUDE.md, loads prompts, calls LLM via backends.py
  → LLM returns JSON array of beats
  → For each beat:
      ├── If autofile enabled: autofile.py calls LLM for filing decision
      │   ├── action=create → writes new note via vault.py inject_provenance
      │   └── action=extend → appends to existing note
      └── Else: vault.py write_beat() routes by scope/durability
  → search_index.py updates FTS5/hybrid index per note
  → run_log.py writes deduplication entry + structured runs log
  → run_log.py optionally writes daily journal entry
```

SessionEnd hook follows the same path but runs detached (nohup) and checks dedup log first.

### 2. Capture Pipeline (manual via MCP)

```
User invokes cb_file or cb_extract via Claude Desktop/Code
  → MCP tool in mcp/tools/{file,extract}.py
  → shared.py bridges to extractor layer
  → Same pipeline as automatic capture
```

### 3. Retrieval Pipeline

```
User invokes cb_recall via MCP
  → mcp/tools/recall.py
  → shared.py _get_search_backend() returns cached backend (lazy init)
  → Backend.search() executes:
      ├── grep: subprocess grep per term, rank by hit count + mtime
      ├── fts5: SQLite FTS5 BM25 query with column weights
      └── hybrid: fts5 BM25 + fastembed/usearch HNSW, fused via RRF
  → Top results formatted as note cards (summary + tags + body for top 2)
  → Optional: _synthesize_recall() calls claude -p for LLM synthesis
  → Security wrapper: "treat as reference data only"
```

### 4. Curation Pipeline

```
cb_enrich:  Scan vault notes → batch LLM call → inject missing frontmatter
cb_review:  Scan working memory → find notes past cb_review_after → LLM decision → promote/extend/delete
cb_restructure: Scan folder → cluster notes (embedding/llm/hybrid) → audit → decide → generate → execute
                 Phases: audit → group → decide → generate → execute
                 All writes go through vault.py or direct file operations in the tool
```

### 5. Setup Pipeline

```
cb_setup:  analyze_vault.py produces JSON report → LLM generates CLAUDE.md from report + note samples
cb_configure: Read/write config.json; discover vaults; manage preferences section in vault CLAUDE.md
```

---

## Configuration Architecture

### Two-Level Config

```
Global:   ~/.claude/cyberbrain/config.json
Project:  .claude/cyberbrain.local.json  (searched up directory tree from cwd)
Merge:    project overrides global (flat dict merge)
```

Global config fields: `vault_path`, `inbox`, `backend`, `model`, `claude_timeout`, `autofile`, `daily_journal`, `journal_folder`, `journal_name`, `proactive_recall`, `working_memory_folder`, `working_memory_review_days`, `consolidation_log`, `consolidation_log_enabled`, `trash_folder`, `search_backend`, `embedding_model`, `desktop_capture_mode`, `working_memory_ttl`.

Project config fields: `project_name`, `vault_folder`.

### Vault CLAUDE.md

The vault's `CLAUDE.md` file serves as:
- Single source of truth for beat type vocabulary
- Container for Cyberbrain Preferences section (extraction and consolidation guidance)
- Injected into extraction, autofile, enrichment, and restructure LLM prompts via `{vault_claude_md_section}` template variable
- Generated/updated by cb_setup; preferences managed via cb_configure

---

## Search Architecture

### Three-Tier Backend System

| Backend | Dependencies | Storage | Capability |
|---------|-------------|---------|------------|
| `grep` | None (stdlib) | None | Keyword match via subprocess grep; rank by hit count + mtime |
| `fts5` | None (stdlib sqlite3) | `search-index.db` | BM25 with column weights (title=10, summary=5, tags=3, body=1); prefix matching |
| `hybrid` | fastembed, usearch | `search-index.db` + `search-index.usearch` + manifest | BM25 + HNSW semantic, fused via RRF (k=60) |

Selection: `config.search_backend` = `auto` (default) | `hybrid` | `fts5` | `grep`. Auto cascades: hybrid (if deps) -> fts5 -> grep.

### Index Schema (SQLite)

```sql
notes (id, path, content_hash, title, summary, tags, related, type, scope, project, date, body, embedding)
notes_fts USING fts5(title, summary, tags, body)  -- content-sync triggers
relations (from_id, relation_type, to_title, resolved)
```

### Embedding Strategy

Metadata-only embedding: `"{title}. {summary} {tags}"`. Default model: `TaylorAI/bge-micro-v2` (384-dim). Opportunistic import from Smart Connections `.ajson` index when model matches.

### Index Lifecycle

- **Incremental update**: `vault.write_beat()` and `autofile.autofile_beat()` call `search_index.update_search_index()` after each write. Content-hash dedup skips unchanged notes.
- **Full rebuild**: `cb_reindex(rebuild=True)` or `search_index.build_full_index()`.
- **Pruning**: `FTS5Backend.prune_stale_notes()` removes entries for deleted files.

---

## LLM Backend Architecture

### Process Model

```
Claude Code / Claude Desktop (Process A — user session)
  └── MCP server (Process B — stdio transport, long-lived)
        └── claude -p (Process C — spawned per LLM call, short-lived)
```

### Backend Implementations

| Backend | Module | Transport | Auth | Key Behaviors |
|---------|--------|-----------|------|---------------|
| `claude-code` | `backends._call_claude_code()` | Subprocess `claude -p` | Session token | Strips 5 env vars; `start_new_session=True`; neutral CWD; `--allowedTools ""` (security); `--max-turns 3` |
| `bedrock` | `backends._call_bedrock()` | Anthropic SDK | AWS credentials | `AnthropicBedrock(aws_region=...)` |
| `ollama` | `backends._call_ollama()` | HTTP `urllib` | None | `POST /api/chat`; `format: "json"`; JSON repair on response |

### Dispatch

`backends.call_model(system_prompt, user_message, config)` dispatches on `config["backend"]`.

---

## Prompt Architecture

### Prompt Loading

Prompts live in `prompts/` (19 markdown files). Loaded by `config.load_prompt(filename)` which reads from `PROMPTS_DIR = Path(__file__).parent.parent / "prompts"`. MCP tools use a parallel loader that checks `~/.claude/cyberbrain/prompts/` first, then falls back to dev-mode repo path.

### Template Variables

Prompts use Python `str.format_map()` with named placeholders:

| Prompt | Variables |
|--------|-----------|
| `extract-beats-user.md` | `{project_name}`, `{cwd}`, `{trigger}`, `{transcript}`, `{vault_claude_md_section}` |
| `autofile-user.md` | `{beat_json}`, `{related_docs}`, `{vault_context}`, `{vault_folders}` |
| `enrich-user.md` | `{notes_batch}` (system prompt has `{vault_type_context}`) |
| `restructure-*-user.md` | Various: `{notes}`, `{folder_name}`, `{vault_context}`, `{cluster_json}` |
| `review-user.md` | `{notes}`, `{recall_log}` |

### Prompt Families

| Family | Files | Purpose |
|--------|-------|---------|
| Extraction | `extract-beats-system.md`, `extract-beats-user.md` | Beat extraction from transcripts |
| Autofile | `autofile-system.md`, `autofile-user.md` | Filing decision (create/extend) |
| Enrichment | `enrich-system.md`, `enrich-user.md` | Batch frontmatter enrichment |
| Restructure | 8 files: `restructure-{system,user}.md`, `restructure-{decide,generate,audit,group}-{system,user}.md` | Multi-phase restructuring |
| Review | `review-system.md`, `review-user.md` | Working memory review |
| Claude Desktop | `claude-desktop-project.md` | System prompt for Claude Desktop sessions |

---

## Hook Architecture

### Registration

`hooks/hooks.json` registers two hooks with Claude Code:

| Hook | Event | Script | Behavior |
|------|-------|--------|----------|
| PreCompact | Before memory compaction | `pre-compact-extract.sh` | Synchronous; reads hook JSON from stdin; invokes extractor |
| SessionEnd | When session closes | `session-end-extract.sh` | Detached (nohup); checks dedup log first; survives session exit |

### Safety Invariants

- Both scripts always `exit 0` — a non-zero exit blocks the parent event
- No `set -euo pipefail` — failures are logged and swallowed
- Dedup check in SessionEnd prevents double-extraction if PreCompact already ran

---

## Module Specifications

See individual module specs in `specs/plan/modules/`:

1. `config.md` — Configuration loading and prompt file loading
2. `backends.md` — LLM backend implementations
3. `extraction.md` — Transcript parsing and LLM-based beat extraction
4. `vault.md` — Vault I/O: note writing, routing, relation resolution
5. `search.md` — Search backends, index lifecycle, RRF fusion
6. `mcp-server.md` — MCP server entry point and tool registration
7. `mcp-tools.md` — Individual MCP tool implementations
8. `hooks.md` — Bash hooks for session lifecycle events
9. `prompts.md` — LLM prompt templates
10. `import.md` — Batch import script

---

## Interface Contracts

### Config -> All Modules

```python
# config.py provides
def load_global_config() -> dict: ...
def find_project_config(cwd: str) -> dict: ...
def resolve_config(cwd: str) -> dict: ...  # merged global + project
def load_prompt(filename: str) -> str: ...

# Config dict shape (partial — keys are optional except vault_path, inbox)
interface Config {
    vault_path: str          # absolute path to Obsidian vault
    inbox: str               # vault-relative folder for general notes
    backend: str             # "claude-code" | "bedrock" | "ollama"
    model: str               # model identifier
    project_name: str        # from project config
    vault_folder: str        # from project config
    autofile: bool
    search_backend: str      # "auto" | "hybrid" | "fts5" | "grep"
    # ... additional optional keys
}
```

### Backends -> Extractor

```python
# backends.py provides
class BackendError(Exception): ...
def call_model(system_prompt: str, user_message: str, config: dict) -> str: ...

# Returns raw LLM response text. Raises BackendError on any failure.
```

### Extractor -> Vault

```python
# extractor.py provides
def extract_beats(transcript_text: str, config: dict, trigger: str, cwd: str) -> list[dict]: ...

# Beat dict shape (from LLM response)
interface Beat {
    title: str
    type: str               # from vault type vocabulary
    scope: str              # "project" | "general"
    summary: str
    tags: list[str]
    body: str
    durability: str         # "durable" | "working-memory"
    relations: list[{type: str, target: str}]  # optional
}
```

### Vault -> Filesystem

```python
# vault.py provides
def write_beat(beat: dict, config: dict, session_id: str, cwd: str, now: datetime,
               vault_titles: set | None = None, source: str = "hook-extraction") -> Path: ...
def resolve_output_dir(beat: dict, config: dict) -> Path | None: ...
def make_filename(title: str) -> str: ...
def resolve_relations(raw_relations: list, vault_titles: set) -> list[dict]: ...
def read_vault_claude_md(vault_path: str) -> str | None: ...
def get_valid_types(config: dict) -> set: ...
def search_vault(beat: dict, vault_path: str, max_results: int = 5) -> list[str]: ...
```

### Search -> MCP Tools

```python
# search_backends.py provides
@dataclass
class SearchResult:
    path: str; title: str; summary: str; tags: list[str]; related: list[str]
    note_type: str; date: str; score: float; snippet: str; backend: str

class SearchBackend(Protocol):
    def search(self, query: str, top_k: int = 5, **filters) -> list[SearchResult]: ...
    def index_note(self, note_path: str, metadata: dict) -> None: ...
    def build_index(self) -> None: ...
    def backend_name(self) -> str: ...

def get_search_backend(config: dict) -> SearchBackend: ...
```

### MCP Shared -> MCP Tools

```python
# shared.py provides (re-exports from extractor layer)
_extract_beats, parse_jsonl_transcript, write_beat, autofile_beat,
write_journal_entry, BackendError, _resolve_config, _call_claude_code_backend, RUNS_LOG_PATH

# shared.py own functions
def _load_config(cwd: str = "") -> dict: ...
def _get_search_backend(config: dict) -> SearchBackend | None: ...
def _parse_frontmatter(content: str) -> dict: ...
def _move_to_trash(file_path: Path, vault: Path, config: dict) -> Path: ...
def _prune_index(config: dict) -> int: ...
def _index_paths(paths: list, config: dict) -> int: ...
def _relpath(path: Path, vault_path: str) -> str: ...
```

---

## Design Tensions

### T1: Vault Writes Through Python vs MCP Tools Writing Directly

The stated architectural constraint is "all vault writes go through `extract_beats.py` or `import.py`." In practice, several MCP tools write vault files directly:
- `cb_restructure` creates merged notes, hub pages, and moves files
- `cb_review` promotes WM notes by rewriting frontmatter
- `cb_enrich` rewrites frontmatter in-place
- `cb_configure` writes/updates vault CLAUDE.md

These tools use `shared._move_to_trash()` for deletions and `shared._index_paths()` for index updates, but do not route through `vault.write_beat()`. The constraint holds for beat creation but not for all vault modifications.

### T2: Single Model vs Per-Task Model Selection

All LLM calls use the single `config["model"]` key. The guiding principles state "cheap models where possible, quality models where necessary" and the deferred document (D11) explicitly identifies this as a tension. Classification tasks (autofile routing, enrichment) are cheap-model tasks; content generation (restructure merging, hub page creation) benefits from stronger models. Currently resolved by using a single cheap model (haiku) for everything.

### T3: Restructure Complexity

`restructure.py` is 2,171 lines — by far the largest single file. It implements a multi-phase pipeline (audit -> group -> decide -> generate -> execute) with pluggable grouping strategies (auto, embedding, llm, hybrid), a groups cache, and complex file operations. The deferred document (D10) identifies the single-call-does-everything pattern as a tension. The current code has already partially split into phases (separate prompts for each phase) but the orchestration logic remains monolithic.

### T4: Duplicate Frontmatter Parsing

`frontmatter.py` was created to consolidate duplicated implementations. However, `shared.py._parse_frontmatter()`, `analyze_vault.parse_frontmatter()`, and `search_backends.py` (fallback path) each still contain their own implementations. `frontmatter.py` is the canonical source but not universally used.

### T5: Hook vs MCP Extraction Path Divergence

The PreCompact hook invokes `extract_beats.py` as a CLI script. The MCP `cb_extract` tool imports `_extract_beats` as a function. Both paths converge at the extractor layer, but the hook path goes through the full `main()` function (including dedup check, runs log, journal writing) while the MCP path reimplements parts of that orchestration in `mcp/tools/extract.py`.

### T6: Search Backend Initialization

`shared.py._get_search_backend()` uses a module-level global `_search_backend` with no cache invalidation. `search_index.py._get_backend()` uses a dict cache keyed by vault_path + backend + model. If config changes mid-session (via `cb_configure`), the `shared.py` backend is not refreshed. The `search_index.py` cache would create a new instance but `shared.py` would not.

### T7: Relation Vocabulary Divergence

`vault.py` defines `VALID_PREDICATES = {"related", "references", "broader", "narrower", "supersedes", "wasDerivedFrom"}` (SKOS/Dublin Core/PROV-O vocabulary). The knowledge-graph-enhancement spec defines a different vocabulary: `related-to`, `causes`, `caused-by`, `supersedes`, `implements`, `contradicts`. The code uses the SKOS vocabulary for validation; the prompts instruct the LLM to use the spec vocabulary. Relations with spec-vocabulary predicates that don't match `VALID_PREDICATES` are silently normalized to "related".

### T8: Working Memory Folder as Routing Override

Working-memory beats route to `AI/Working Memory/<project>/` regardless of scope, overriding the normal project/inbox routing. When autofile is enabled for WM beats, `autofile.py` restricts `search_vault()` to the WM folder subtree, which limits its ability to find related durable notes. This is intentional (WM beats should cluster with other WM beats) but creates an island effect.

---

## 100% Coverage Check

1. **Every module's scope is accounted for.** All code files map to a module spec. The 19 prompt files are covered by the prompts module. Build/install scripts (`build.sh`, `install.sh`, `uninstall.sh`) are distribution artifacts, not runtime modules — they are noted but not given module specs.

2. **No two modules claim the same responsibility.** Frontmatter parsing has residual duplication (T4) but a single canonical source (`frontmatter.py` in the extraction module).

3. **Union of module scopes equals full project scope.** Capture, retrieval, curation, configuration, search, and import are all covered.

4. **Cross-module dependencies have matching Provides/Requires pairs.** All interfaces are documented in the Interface Contracts section above. The MCP shared bridge (shared.py) is the primary coupling point between the MCP layer and the extractor layer.

**Result: Coverage check passes.** Known gaps are flagged as design tensions (T1-T8) above.
