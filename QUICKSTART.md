# Quick Start

## Install

```bash
git clone https://github.com/your-org/cyberbrain
cd cyberbrain
bash install.sh
```

---

## Configure

### Step 1 — Point at a vault

Edit `~/.claude/cyberbrain.json`:

```json
{
  "vault_path": "/absolute/path/to/your/vault",
  "inbox": "AI/Claude-Sessions",
}
```

**Don't have an Obsidian vault yet?**
Create a new vault in Obsidian, then set `vault_path` to that directory. The folders above will be created automatically.

**Don't use Obsidian?**
Set `vault_path` to any existing directory. Notes are plain markdown — any editor works.

---

### Step 2 — Choose a backend

**Default — uses your Claude Code subscription, no API key needed:**

```json
{ "backend": "claude-code" }
```

**AWS Bedrock:**

```json
{
  "backend": "bedrock",
  "bedrock_region": "us-east-1"
}
```
Requires AWS credentials configured (`~/.aws/credentials` or env vars).

**Local model (Ollama):**

```json
{
  "backend": "ollama",
  "model": "llama3.2",
  "ollama_url": "http://localhost:11434"
}
```
Requires Ollama running locally with a model pulled.

---

## Verify

Start a Claude Code session in any project. Run `/compact` (or let context fill naturally). You'll see **"Extracting knowledge before compaction..."** in the status bar. Beats appear in your vault under `AI/Claude-Sessions/`.

To preview what would be extracted from the current session without writing anything:
```
/cb-extract --dry-run
```

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

If you have an existing vault, run this once to generate a `CLAUDE.md` at the vault root. It teaches Claude your vault's structure so that `/cb-file` and future extractions stay consistent with your conventions:

```
/cb-setup
```

For a new vault, skip this until you have a few dozen notes.

---

## Skills reference

| Command | What it does |
|---|---|
| `/cb-extract` | Extract beats from the current session (or a path to any `.jsonl`) |
| `/cb-recall <query>` | Search your vault and inject context into the session |
| `/cb-file` | Manually save any piece of information to the vault |
| `/cb-enrich` | Backfill metadata on notes that are missing tags/summaries |
| `/cb-setup` | Analyze vault and generate/update its `CLAUDE.md` |

---

## Troubleshooting

**No beats appear after /compact**
Check `vault_path` in `~/.claude/cyberbrain.json` points to a real directory, and that the hook is registered: `cat ~/.claude/settings.json | grep PreCompact`

**"Reached max turns" or backend error**
The transcript may be very long. Add `"claude_timeout": 180` to `~/.claude/cyberbrain.json` to extend the timeout.

**Beats land in inbox instead of project folder**
Confirm `.claude/cyberbrain.local.json` exists in the project root (or a parent directory up to `~`).

**Skills not found after install**
Skills load at session start. Open a new Claude Code session after running `bash install.sh`.
