# Quick Start

## Prerequisites

- `uv` — [brew install uv](https://docs.astral.sh/uv/getting-started/installation/)

---

## Install

```bash
# Add plugin marketplace (one time)
claude plugin marketplace add devnill/cyberbrain

# Install the plugin
claude plugin install cyberbrain@devnill-cyberbrain
```

---

## Configure

Run `/cyberbrain:config` in Claude Code. This walks you through vault path selection, folder structure, and default preferences.

---

### Manual Configuration

For advanced users who prefer to edit config files directly.

**Vault path** — edit `~/.claude/cyberbrain/config.json`:

```json
{
  "vault_path": "/absolute/path/to/your/vault",
  "inbox": "AI/Claude-Sessions"
}
```

**Don't use Obsidian?**
Set `vault_path` to any directory. Notes are plain markdown — any editor works.

**Backend selection:**

Default — uses your Claude Code subscription, no API key needed:

```json
{ "backend": "claude-code" }
```

AWS Bedrock:

```json
{
  "backend": "bedrock",
  "bedrock_region": "us-east-1"
}
```
Requires AWS credentials configured (`~/.aws/credentials` or env vars).

Local model (Ollama):

```json
{
  "backend": "ollama",
  "model": "llama3.2",
  "ollama_url": "http://localhost:11434"
}
```
Requires Ollama running locally with a model pulled.

**Recommended model sizes for local inference:**

| Tool | Minimum | Recommended |
|---|---|---|
| `cb_extract`, `cb_enrich`, `cb_recall` | 7B | 14B+ |
| `cb_restructure` | 14B | 32B+ |

`cb_restructure` requires the strongest reasoning — it must classify clusters, decide between merge/hub-spoke/subfolder, and generate full note content in a single call. Models below 14B frequently return malformed JSON or omit required frontmatter fields. 32B+ models (e.g. Qwen2.5-32B, Mistral-Small) produce reliably usable output.

---

## Verify

Start a Claude Code session in any project. Run `/compact` (or let context fill naturally). You'll see **"Extracting knowledge before compaction..."** in the status bar. Beats appear in your vault under `AI/Claude-Sessions/`.

---

## Claude Desktop Quick Start

The installer registers the MCP server in Claude Desktop automatically (macOS). After installation, restart Claude Desktop — a hammer icon in the chat input confirms it's connected.

**If you're a Claude Desktop user who doesn't use Claude Code**, this is your primary interface for cyberbrain.

### Step 1 — Open a Project

In Claude Desktop: **Projects** → create or open a project → **Customize** → **Custom instructions**.
Paste the contents of `prompts/claude-desktop-project.md`. This teaches Claude to use the vault tools.

### Step 2 — Configure through conversation

The installer creates `~/.claude/cyberbrain/vault/` as a default vault. You don't need to edit any config files. To switch to an Obsidian vault, just ask Claude:

> "Set up my cyberbrain vault"

Claude will call `cb_configure(discover=True)` to find Obsidian vaults on your Mac and guide you through picking one.

You can also configure settings directly:
- **Find vaults:** ask "Find my Obsidian vaults"
- **Set vault:** ask "Use my vault at ~/Documents/MyVault"
- **Change capture behavior:** ask "Set capture mode to auto" (files immediately), "to suggest" (offers first), or "to manual" (only when asked)

### Step 3 — Start a session

Use the `orient` prompt from the `+` menu at session start. This loads your behavioral guide and checks vault health automatically.

Or just start working — Claude will:
- Search your vault when you mention familiar projects or topics
- Offer to save valuable knowledge (in `suggest` mode) or save it automatically (in `auto` mode)

---

## Using with Claude Desktop (optional)

See the **Claude Desktop Quick Start** section above for full setup instructions.

**If the server isn't connecting:** go to **Settings → Developer → Edit Config** and verify the `cyberbrain` entry is present in `mcpServers`. See the README for the manual config format.

---

## Import existing history (optional)

### From Claude.ai / Claude Desktop

Request a data export at **claude.ai → Settings → Privacy → Export Data**.
Extract the ZIP, then run:

```bash
python3 scripts/import.py --export ~/Downloads/claude-export/ --format claude
```

Re-run on newer exports safely — already-imported conversations are skipped.

### From ChatGPT

Export your data at **chatgpt.com → Settings → Data controls → Export data**.
Extract the ZIP, then run:

```bash
python3 scripts/import.py --export ~/Downloads/chatgpt-export/ --format chatgpt
```

### Preview before importing

```bash
python3 scripts/import.py --export ~/Downloads/export/ --format claude --dry-run
```

---

## Route beats to a project folder (optional)

Without this, all beats land in `AI/Claude-Sessions/`. To route a project's beats to a dedicated folder, add `.claude/cyberbrain.local.json` to the project root:

```json
{
  "project_name": "my-app",
  "vault_folder": "Projects/my-app/Claude-Notes"
}
```

The system walks up from the session's working directory to find this file.

---

## Generate vault filing instructions (optional)

If you have an existing vault, ask Claude to analyze it and generate a `CLAUDE.md` at the vault root. This teaches Claude your vault's structure so extractions and filings stay consistent with your conventions:

> "Analyze my vault and set it up for cyberbrain"

Claude will call `cb_setup` with a two-phase flow: first it analyzes the vault and asks clarifying questions, then it generates the CLAUDE.md.

For a new vault, skip this until you have a few dozen notes.

---

## MCP tools reference

| Tool | What it does |
|---|---|
| `cb_extract` | Extract beats from a transcript file and file them to the vault |
| `cb_recall` | Search your vault and inject context into the session |
| `cb_read` | Read a specific vault note by path or title |
| `cb_file` | Manually save any piece of information to the vault |
| `cb_enrich` | Backfill metadata on notes that are missing tags/summaries |
| `cb_setup` | Analyze vault and generate/update its `CLAUDE.md` (two-phase) |
| `cb_configure` | View or change config, vault path, capture mode, and preferences |
| `cb_status` | Show vault health, index stats, and recent extraction runs |
| `cb_restructure` | Find and merge over-fragmented notes using semantic clustering |
| `cb_review` | Review working memory notes that are due — promote, extend, or delete |

---

## Troubleshooting

**No beats appear after /compact**
Check `vault_path` in `~/.claude/cyberbrain/config.json` points to a real directory, and that the hook is registered: `grep PreCompact ~/.claude/settings.json`

**"Reached max turns" or backend error**
The transcript may be very long. Add `"claude_timeout": 180` to `~/.claude/cyberbrain/config.json` to extend the timeout.

**Beats land in inbox instead of project folder**
Confirm `.claude/cyberbrain.local.json` exists in the project root (or a parent directory up to `~`).

**MCP tools not available in Claude Desktop**
Restart Claude Desktop and verify the `cyberbrain` entry is present in Settings → Developer → Edit Config under `mcpServers`.
