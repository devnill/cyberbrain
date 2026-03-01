# SP9: Claude Desktop Integration — Friction Reduction

**Date:** 2026-02-27
**Status:** Investigation complete

---

## Part 1: MCP Server Audit

### 1.1 Tool Signatures and Docstrings

#### `kg_extract`

```python
def kg_extract(
    conversation: str,
    project_name: str = "",
    cwd: str = "",
    trigger: str = "manual",
) -> str:
```

**Docstring:** "Extract knowledge beats from conversation text and file them into the Obsidian vault. Pass the full text of a conversation (any format: plain text, Human/Assistant turns, or Claude Code JSONL). Beats will be extracted by Claude and filed according to the autofile setting in ~/.claude/knowledge.json. Returns a summary of every note created or extended."

This is the richest tool — it calls the full extraction pipeline (LLM, beat parsing, autofile or flat write, journal). Conversations over 150,000 characters are tail-truncated.

#### `kg_file`

```python
def kg_file(
    title: str,
    body: str,
    type: str = "reference",
    tags: list[str] | None = None,
    scope: str = "general",
    summary: str = "",
) -> str:
```

**Docstring:** "File a single note into the Obsidian vault. Use this to capture a specific piece of information — a decision, insight, reference, or pattern — without going through full beat extraction."

Bypasses LLM extraction — writes a beat directly. Always uses `_load_config()` without `cwd`, so per-project routing (`knowledge.local.json`) is never consulted. Project-scoped beats filed via `kg_file` will land in the wrong folder if the vault has project-specific routing configured.

#### `kg_recall`

```python
def kg_recall(query: str, max_results: int = 5) -> str:
```

**Docstring:** "Search the Obsidian vault for notes relevant to a query. Returns the content of the most relevant notes, ranked by recency among those that match. Use this to retrieve context from past sessions before starting new work on a topic."

This is the primary retrieval interface. It splits the query into individual terms (3+ characters, up to 8 terms), runs a separate `grep -r -l` per term, merges matches by file path, then sorts by modification time (most recent first) and returns the top N file contents (truncated at 3,000 characters each). Returns a plain text string.

---

### 1.2 Implementation Issues

#### Error handling

- **`kg_recall`**: The `subprocess.run` call to `grep` has no timeout. If the vault is large and grep runs slowly, the MCP request will hang indefinitely. No `timeout` parameter is passed to `subprocess.run`. The `capture_output=True` mitigates subprocess output blocking but not duration.
- **`kg_recall`**: An OSError from `os.path.getmtime` is silently swallowed. This is acceptable defensive coding but produces no log entry.
- **`kg_extract`**: The per-beat `except Exception as e` catches all errors during write/autofile, and each failure is recorded in the returned summary string as `✗ title: error`. This is good — failures don't abort the whole extraction. But the error message surfaced in the return string may be too terse for diagnosing misconfiguration.
- **`kg_file`**: A top-level `except Exception as e` is the only guard. Returns `"Error filing note: {e}"` as a string. The MCP call itself succeeds (returns a string), so Claude Desktop shows no error indicator — the user sees only the returned string, which could be missed.
- All tools: no timeout on the overall MCP tool call. `kg_extract` makes an LLM call internally (via `call_model`) which has a configurable timeout (`claude_timeout` in config, defaulting to 120s), but MCP itself has no enforced call-level timeout. A slow LLM backend could leave the MCP call spinning.

#### Return format

- **`kg_recall`** returns raw note content preceded by a header line. Individual notes are separated by `---`. Each note is prefixed by its vault-relative file path as a `### heading`. Content is truncated at 3,000 characters per note.
- The return is a single unstructured string. Claude receives the full text as a tool result and must reason about it without any structural hints beyond markdown headers. There is no explicit separation between frontmatter metadata and body content in the returned text, no relevance score, and no indication of which search terms matched.
- **`kg_extract`** returns a plain summary: `"Extracted N/M beat(s):\n\n✓ [type] title → path\n✗ title: error"`. Useful as a human-readable confirmation but not machine-parseable.
- **`kg_file`** returns either `"Filed: relative/path"` or `"Error filing note: ..."`. Minimal.

#### Config resolution

- **`kg_recall`** and **`kg_file`** call `_load_config()` with no `cwd` argument, which means they always call `resolve_config(str(Path.home()))`. This means per-project vault folder routing from `.claude/knowledge.local.json` is never applied in these tools. Only `kg_extract` accepts and uses a `cwd` argument — and even there, `cwd` defaults to the empty string, which also falls back to `Path.home()`.
- In practice, `kg_recall` searches the entire vault regardless of project context, which is actually the correct behavior for recall. But `kg_file` always routes to the inbox or staging folder even when a project vault folder would be appropriate, because it never loads project config.

#### Import path fragility

- `server.py` does `sys.path.insert(0, str(Path.home() / ".claude" / "extractors"))` to find `extract_beats`. This hardcodes the installed path. When running in plugin mode (via `--plugin-dir`), the server is invoked from the plugin directory (`mcp/server.py` in the repo), but `extract_beats` is still expected at `~/.claude/extractors/`. If the system is used via `--plugin-dir` without running `install.sh` first, the import will fail with no clear error message to the user.
- There is no try/except around the `from extract_beats import ...` calls inside tool functions. If the import fails, the tool call itself will raise an exception, which FastMCP will convert to an MCP error response. The error text will contain the Python traceback, which is technically visible but not user-friendly.

---

### 1.3 MCP Registration

#### Plugin mode (`.mcp.json` in repo root)

```json
{
  "mcpServers": {
    "knowledge-graph": {
      "command": "python3",
      "args": ["mcp/server.py"]
    }
  }
}
```

This uses bare `python3` (system Python, whichever is first on PATH) and a relative path to `mcp/server.py`. The `mcp` package is expected to be importable from whichever `python3` resolves to. This will fail if the system Python doesn't have `mcp` installed. It does not use the venv that `install.sh` creates.

#### Claude Desktop registration (installed mode)

`install.sh` registers the server in `~/Library/Application Support/Claude/claude_desktop_config.json` as:

```json
{
  "command": "~/.claude/mcp-venv/bin/python3",
  "args": ["~/.claude/mcp/server.py"]
}
```

This uses the venv Python explicitly and points to the installed copy of `server.py`. This is the correct approach for installed mode.

#### Venv state: `mcp` package is NOT installed

Inspection of `~/.claude/mcp-venv/lib/python3.14/site-packages/` shows only `pip` is present. The `mcp` package (FastMCP) is absent. This means the MCP server cannot start: importing `from mcp.server.fastmcp import FastMCP` will raise `ModuleNotFoundError`.

The `install.sh` script attempts to install `mcp` with:
```bash
"$MCP_VENV/bin/pip" install mcp -q 2>/dev/null
```

The silent `2>/dev/null` suppression means any failure during `pip install mcp` is discarded without user notification beyond a `[WARN]` line. It is likely that the `pip install mcp` step failed silently at install time, leaving the venv empty. The current state is that the MCP server is registered in Claude Desktop but will fail on startup every time Claude Desktop is launched.

**This is the most critical issue identified.** The MCP server is non-functional in its current state.

---

## Part 2: Friction Analysis

### 2.1 Tool Invocation Friction

The user must explicitly prompt Claude to use the vault tools. There is no automatic invocation. Claude Desktop has no hook equivalent to Claude Code's PreCompact hook — it is purely reactive to user or model-initiated tool calls.

In practice this means:
- The user opens a Claude Desktop conversation, starts asking questions, and the vault is never consulted unless the user explicitly says something like "check my knowledge base" or "search my notes for X."
- Claude will not spontaneously use `kg_recall` even when the topic clearly matches something that would be in the vault, because there is no instruction telling it to do so proactively.
- The tools have reasonable docstrings (`"Use this to retrieve context from past sessions before starting new work on a topic"`), but Claude's default behavior is to answer from its own knowledge unless told otherwise. Tool use is not the default; it's the exception.

### 2.2 Return Format

`kg_recall` returns a raw concatenation of note content as a single string. The format looks like:

```
Found 3 note(s) matching 'redis cache eviction':

### AI/Claude-Sessions/2025-11-03-redis-ttl.md

---
id: abc123
date: 2025-11-03
type: error-fix
...
---

## Redis TTL eviction policy causing cache stampede

When all keys share the same TTL...

[content truncated at 3000 chars]

---

### Projects/my-api/Claude-Notes/cache-strategy.md

...
```

Problems with this format:
- **No relevance ordering signal.** Notes are sorted by modification time, not by relevance to the query. The most recently modified note is first, even if it's only tangentially related.
- **Frontmatter is dumped raw.** The YAML frontmatter is included in the content string — Claude must parse it as text. There's no pre-parsed summary extraction despite the beat format having a dedicated `summary` field designed for exactly this purpose.
- **Content is chopped arbitrarily.** The 3,000-character truncation can cut in the middle of a sentence or code block, producing garbled context.
- **No per-note relevance metadata.** The return string gives Claude no signal about which terms matched which notes, what the type/scope/date of each note is (without parsing frontmatter), or how confident the retrieval is.
- **Token cost is high.** Five notes at up to 3,000 characters each = up to 15,000 characters of raw markdown dumped into Claude's context. Much of this is frontmatter fields Claude doesn't need.

### 2.3 Session Start: Automatic Vault Consultation

There is no mechanism in Claude Desktop that automatically invokes `kg_recall` at session start. Claude Desktop does offer:

- **Projects**: A "Project" in Claude Desktop allows setting a persistent system prompt and uploading reference files. This is the closest analog to automatic context injection.
- **Custom instructions**: Can be set per-Project or globally.
- **Memory** (Claude.ai web): The claude.ai web interface has a Memory feature that automatically injects user facts. This is not currently available in Claude Desktop's MCP integration layer.

The current system has no mechanism to make vault consultation automatic. Even if a system prompt told Claude "always search the vault at session start," Claude would need to execute `kg_recall` as its first action — which it may or may not do reliably, and which requires a turn to complete before the user can start asking questions.

### 2.4 Tool Discoverability and Proactive Use

Claude's default behavior when it has MCP tools available is to use them reactively — when explicitly asked, or when it can infer from context that a tool call is needed. The vault tools' docstrings describe their purpose correctly, but they do not signal urgency or frequency of use.

Without a system prompt instructing proactive behavior, Claude will:
- Answer questions from its own training data without checking the vault
- Not call `kg_recall` at the start of a session
- Use `kg_recall` if the user explicitly asks, or if the user says something like "I think I've worked on this before"
- Not distinguish between topics where the vault might have relevant notes and topics where it won't

A system prompt that produces more proactive behavior would need to:
1. Tell Claude the vault exists and what it contains (past session knowledge, filed notes)
2. Instruct Claude to consult it at session start
3. Instruct Claude to consult it mid-session when the topic could have prior context
4. Specify what kinds of queries are vault-appropriate vs. general knowledge

### 2.5 Error Visibility

When the MCP server fails:
- **Server startup failure** (e.g., `mcp` package not installed): Claude Desktop will show a connection error for the server. In practice this appears as the tools being unavailable — when the user tries to use them, there's no tool to call. Claude may not even know the tools exist. The user may not notice unless they check Claude Desktop's settings or observe that tool calls never appear.
- **Tool call failure** (e.g., `vault_path` not configured): The MCP protocol returns a tool error, which Claude Desktop surfaces as an error message in the tool result. Claude will see the error text and typically relay it to the user. This is visible but the error messages in the current code are terse: `"Error filing note: [exception text]"`.
- **Silent logical failure** (e.g., vault path exists but is empty): `kg_recall` returns `"No notes found matching: X"`. This is a valid response, not an error — Claude will relay it to the user, who may not understand why the vault appears empty.
- **`kg_extract` LLM call failure**: If `call_model` returns empty, the function returns `"No beats extracted — model returned empty response."` This is surfaced to the user but gives no diagnostic detail about whether the LLM call failed, timed out, or returned malformed output.

The most invisible failure is the current state: the `mcp` package is not installed in the venv, so the server never starts, and the user gets no indication that the system is entirely non-functional.

---

## Part 3: Improvements to Spec

### 3.1 Immediate Fix: Install the `mcp` Package

**Priority: blocking.** The MCP server is currently non-functional because the `mcp` Python package is not installed in `~/.claude/mcp-venv/`. The `install.sh` script ran but the `pip install mcp` step silently failed.

To fix manually:
```bash
~/.claude/mcp-venv/bin/pip install mcp
```

To fix in `install.sh`: remove the `2>/dev/null` suppression so failures are visible, and add a post-install verification step:
```bash
if ! ~/.claude/mcp-venv/bin/python3 -c "from mcp.server.fastmcp import FastMCP" 2>/dev/null; then
    echo "  [ERROR] FastMCP import failed after install. MCP server will not work."
    echo "  Run: ~/.claude/mcp-venv/bin/pip install mcp"
fi
```

The venv uses Python 3.14, which is a very recent (pre-release at time of writing) version. The `mcp` package may not have a compatible wheel for Python 3.14. If that's the case, the install script should try to use an older Python (3.11 or 3.12) for the venv, since those have stable wheel availability for MCP dependencies.

### 3.2 System Prompt for Claude Desktop Projects

The right mechanism for proactive vault use is a Claude Desktop Project with a custom system prompt. This system prompt should be stored in the repo (e.g., at `prompts/claude-desktop-project.md`) so users can paste it when setting up a Project in Claude Desktop.

Recommended system prompt:

```
You have access to a personal knowledge vault via MCP tools (kg_recall, kg_file, kg_extract).
This vault contains structured notes extracted from past work sessions — decisions made,
problems solved, bugs fixed, insights discovered, and reference facts. The vault is your
extended memory across sessions.

At the start of every conversation, you should call kg_recall with 1-3 search queries
relevant to the topic being discussed, before responding. Do this even if the user hasn't
asked you to. If the user mentions a project, technology, or problem domain, search for it.

During a conversation:
- If the user mentions a problem they've had before, search the vault for it.
- If you'd normally say "I don't know your project's history" or "I don't have context
  from previous sessions," search the vault instead of saying that.
- If the user says something vault-worthy (a decision, a fix, a pattern), offer to file it
  with kg_file.

When calling kg_recall:
- Use specific technical terms, not vague phrases. "redis eviction policy" not "cache issue."
- Search multiple angles: the technology, the error message, the project name.
- If the first search returns nothing useful, try synonyms or related terms.

The vault is real. Use it.
```

This system prompt addresses the core friction: Claude defaults to not using the vault. The explicit instruction to call `kg_recall` at session start and the "The vault is real. Use it." reinforcement shift the default behavior.

### 3.3 `kg_recall` Return Format Improvements

The current return format dumps raw note content. A better format would:

1. **Pre-extract frontmatter fields** and present them as structured metadata, separate from body content.
2. **Return summaries first, bodies second** — let Claude decide if it needs the full body.
3. **Include match metadata** — which search terms caused each note to be included.
4. **Reduce token cost** — a note's `summary` field is one information-dense sentence designed for exactly this purpose. Return summaries by default; offer a `include_body: bool = False` parameter for full content.

Proposed improved return structure (still a string, but more structured):

```
Found 3 note(s) for 'redis cache eviction' (terms matched: redis, cache, eviction):

[1] Redis TTL eviction causing cache stampede (error-fix, 2025-11-03, project: my-api)
    Summary: All keys shared the same TTL causing simultaneous expiry; fix was to add
             random jitter of ±10% to TTL on write.
    Path: Projects/my-api/Claude-Notes/redis-ttl-fix.md

[2] Cache invalidation strategy decision (decision, 2025-10-28, general)
    Summary: Chose write-through caching over TTL expiry for user session data to avoid
             stampede patterns under load.
    Path: AI/Claude-Sessions/cache-invalidation-decision.md

[3] Redis configuration reference (reference, 2025-09-14, general)
    Summary: Production Redis config: maxmemory-policy allkeys-lru, maxmemory 512mb,
             save disabled for session cache instance.
    Path: AI/Claude-Sessions/redis-config-reference.md

---
Full content for notes above is available. Ask to expand any note by number.
```

This format:
- Uses ~300 tokens instead of ~3,000 for a typical query
- Lets Claude answer from summaries alone for many queries
- Preserves the ability to fetch full content when needed
- Exposes type, date, and project metadata without requiring frontmatter parsing
- Is far easier for Claude to reason about

Implementation requires: a `summary_only: bool = True` parameter on `kg_recall`, extraction of frontmatter fields before returning, and formatting the structured header.

### 3.4 `kg_file` Should Accept `cwd` for Project Routing

Currently `kg_file` always routes to the general inbox because it calls `_load_config()` with no `cwd`. Claude Desktop has no inherent concept of "current working directory," but a user working in a Claude Desktop Project associated with a specific codebase might want project-scoped filing.

Add a `cwd: str = ""` parameter to `kg_file` (matching the pattern in `kg_extract`) so that when a user provides their project's directory, project-scoped routing applies.

### 3.5 Error Message Improvements

- **`kg_file` errors**: Replace `"Error filing note: {e}"` with a diagnostic that includes the vault path being targeted and whether the config was found. E.g.: `"Error filing note to {rel_path}: {e}\n(vault: {config['vault_path']}, config: ~/.claude/knowledge.json)"`
- **`kg_recall` empty result**: When no notes match, include the vault path and the search terms in the response: `"No notes found matching 'query' (searched terms: ['word1', 'word2']) in vault at /path/to/vault. If the vault is empty, run kg_extract on a conversation to start building it."`
- **`kg_extract` model failure**: When `call_model` returns empty, distinguish between empty response and exception. Log the failure to stderr (the MCP server's stderr is visible in Claude Desktop's developer logs).

### 3.6 MCP Server Startup Validation

Add a startup check to `server.py` that verifies the vault is configured and accessible before the server begins serving tools:

```python
# At module load time (before mcp.run()):
try:
    _cfg = _load_config()
    _vault = Path(_cfg.get("vault_path", ""))
    if not _vault.exists():
        import warnings
        warnings.warn(f"Vault path does not exist: {_vault}. kg_recall will return no results.")
except Exception as e:
    import sys
    print(f"[knowledge-graph MCP] Config load failed: {e}", file=sys.stderr)
```

This surfaces config problems at server startup (visible in Claude Desktop's MCP server logs) rather than silently failing per-call.

### 3.7 Plugin Mode `.mcp.json` Fix

The current `.mcp.json` uses bare `python3` without the venv:

```json
{
  "mcpServers": {
    "knowledge-graph": {
      "command": "python3",
      "args": ["mcp/server.py"]
    }
  }
}
```

This will fail if the system `python3` doesn't have `mcp` installed. The plugin-mode config should either:

a) Require the user to install `mcp` in their system Python (bad UX, hard to document)
b) Specify a requirements installation step in `README` and warn if the package is missing
c) Use a `uv run` or `pipx run` invocation that handles dependencies inline (modern approach):

```json
{
  "mcpServers": {
    "knowledge-graph": {
      "command": "uv",
      "args": ["run", "--with", "mcp", "python3", "mcp/server.py"]
    }
  }
}
```

This is the recommended approach for plugin mode: `uv` handles dependency resolution on-demand without requiring manual venv setup.

---

## Summary: Issue Severity Matrix

| Issue | Severity | Effort to Fix |
|---|---|---|
| `mcp` package not installed in venv — server is non-functional | Critical | Low (one pip install; fix install.sh) |
| No proactive vault use at session start | High | Low (write system prompt; add to docs) |
| `kg_recall` return format too verbose, no structure | High | Medium (refactor return format, add summary mode) |
| `kg_file` ignores `cwd`, always routes to inbox | Medium | Low (add cwd param, pass to `_load_config`) |
| No timeout on `grep` subprocess in `kg_recall` | Medium | Low (add timeout= to subprocess.run) |
| Plugin mode `.mcp.json` uses bare python3 | Medium | Low (switch to uv run or document requirement) |
| Error messages too terse for diagnosis | Low | Low (improve error strings) |
| No startup vault validation | Low | Low (add module-level check) |
| `extract_beats` import failure gives unhelpful error | Low | Low (add try/except at import) |

---

## Appendix: What a Good Claude Desktop Session Would Look Like

With a Project system prompt (section 3.2) and the `mcp` package installed, a session should look like:

1. User opens a conversation in the "Development" Project.
2. User says: "I'm having trouble with my Redis cache stampeding under load."
3. Claude immediately calls `kg_recall("redis cache stampede")` and `kg_recall("redis eviction policy")` in parallel.
4. Vault returns a summary-first result including the previously-filed error-fix beat from a past session.
5. Claude responds: "I found a note from a past session about this — last time, the fix was to add jitter to TTL on write (±10%). Here's the relevant detail..." and then addresses the current question with that context already in hand.
6. The user never had to ask Claude to check the vault. The vault was consulted automatically, the right note was found, and the session started with full context from prior work.

This is the target state. The gap between this and the current state is primarily: (a) the broken venv, (b) no system prompt instructing proactive use, and (c) the return format making it harder for Claude to reason about results efficiently.
