# MCP Server Modular Architecture

## Context

`mcp/server.py` was a ~1000-line monolithic file. This refactor splits it into a proper
Python package with clear module boundaries, no behavior changes, and fixes four Pylance-flagged
type bugs.

---

## Layout

```
mcp/
  __init__.py         ← empty (makes mcp/ a Python package)
  server.py           ← entry point: adds mcp/ to sys.path, creates FastMCP, registers modules, calls mcp.run()
  shared.py           ← extractor imports, config helpers, search backend lazy state
  tools/
    __init__.py       ← empty
    extract.py        ← cb_extract tool
    file.py           ← cb_file tool
    recall.py         ← cb_recall + cb_read + _find_note_by_title + _synthesize_recall
    manage.py         ← cb_configure + cb_status + _read_index_stats
  resources.py        ← cyberbrain_guide resource + orient/recall prompts + _build_guide
```

---

## Registration Pattern

Each module exposes a `register(mcp: FastMCP) -> None` function that applies `@mcp.tool()`,
`@mcp.resource()`, and `@mcp.prompt()` decorators to its functions. This avoids the need
to create a global `mcp` instance before the module is imported.

```
shared.py  ←  tools/extract.py
           ←  tools/file.py
           ←  tools/recall.py
           ←  tools/manage.py   (also imports _DEFAULT_* from tools.recall)
           ←  resources.py
               ↑ all imported by server.py which calls register(mcp) on each
```

---

## Import Strategy

`server.py` is run as a script (`python3 server.py`), so relative imports (`from .tools import ...`)
would fail. Instead, `server.py` inserts its own directory into `sys.path[0]`:

```python
_MCP_DIR = Path(__file__).parent
if str(_MCP_DIR) not in sys.path:
    sys.path.insert(0, str(_MCP_DIR))
```

This makes `import shared`, `from tools import extract`, etc. work as flat imports from any
submodule. There is no naming conflict with the installed `mcp` package because `mcp/` has
no `mcp/` subdirectory — Python falls through to the venv's site-packages for `from mcp.server.fastmcp import FastMCP`.

---

## Module Responsibilities

### `mcp/shared.py`
- `sys.path.insert` to `~/.claude/cyberbrain/extractors`
- `try/except ImportError` block importing from `extract_beats` and `frontmatter`
- `_search_backend: None` global + `_get_search_backend(config)` lazy loader
- `_load_config(cwd="") -> dict`
- `_relpath(path, vault_path) -> str`
- Re-exports: `_extract_beats`, `parse_jsonl_transcript`, `write_beat`, `autofile_beat`,
  `write_journal_entry`, `BackendError`, `_resolve_config`, `_call_claude_code_backend`,
  `RUNS_LOG_PATH`, `_parse_frontmatter`

### `mcp/tools/extract.py`
- `cb_extract` inside `register(mcp)`
- `@mcp.tool(annotations=ToolAnnotations(destructiveHint=False))`

### `mcp/tools/file.py`
- `cb_file` inside `register(mcp)`
- `@mcp.tool()`

### `mcp/tools/recall.py`
- `_DEFAULT_DB_PATH`, `_DEFAULT_MANIFEST_PATH` constants
- `_find_note_by_title(title, config)` — FTS5 index lookup
- `_synthesize_recall(query, retrieved_content, config)` — LLM synthesis
- `cb_recall`, `cb_read` inside `register(mcp)`

### `mcp/tools/manage.py`
- `_read_index_stats(config)` — SQLite index stats
- `cb_configure`, `cb_status` inside `register(mcp)`
- Imports `_DEFAULT_DB_PATH`, `_DEFAULT_MANIFEST_PATH` from `tools.recall`

### `mcp/resources.py`
- `_build_guide(recall_instruction, filing_instruction)` — template
- `_get_guide()` — builds guide from current config (called by both resource and orient prompt)
- `cyberbrain_guide`, `orient`, `recall` inside `register(mcp)`

### `mcp/server.py` (entry point)
- Adds `mcp/` dir to `sys.path`
- Creates `mcp = FastMCP("cyberbrain")`
- Imports and calls `register(mcp)` on each module
- `if __name__ == "__main__": mcp.run()`

---

## Type Bug Fixes Applied

| Location | Bug | Fix |
|---|---|---|
| `cb_extract` param | `session_id: str = None` | `session_id: str \| None = None` |
| `cb_recall` body | `results` possibly unbound | initialize `results: list = []` before `if backend:` block |
| `cb_file` body | unused `vault_path` local | not present in this version (was a stale Pylance note) |
| `cb_status` body | unused `backend_name` local | removed the assignment |

---

## install.sh Change

```bash
# Before (single file):
cp "$REPO_DIR/mcp/server.py" "$CB_DIR/mcp/server.py"

# After (full package):
cp -r "$REPO_DIR/mcp/." "$CB_DIR/mcp/"
find "$CB_DIR/mcp" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
```

The Claude Desktop registration path stays `~/.claude/cyberbrain/mcp/server.py` — unchanged.

---

## Invariants

- Tool names, signatures, docstrings, and annotations are identical to the monolith
- `mcp/server.py` remains the registered Claude Desktop entry point
- No behavior changes — pure structural refactor + type bug fixes
- Tests are unaffected (they test extractors, not the MCP server directly)

---

## Verification

```bash
# 1. Python package import check (no runtime errors on import)
cd ~/.claude/cyberbrain/mcp
python3 -c "import shared; print('shared OK')"
python3 -c "from tools import extract, file, recall, manage; print('tools OK')"
python3 -c "import resources; print('resources OK')"

# 2. MCP server starts without error
~/.claude/cyberbrain/venv/bin/python3 ~/.claude/cyberbrain/mcp/server.py &
sleep 2 && kill %1

# 3. Install test — verify all module files are copied
bash install.sh
ls ~/.claude/cyberbrain/mcp/tools/

# 4. Claude Desktop smoke test — restart Claude Desktop, verify cyberbrain tools appear
```
