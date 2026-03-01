# SP2: Daily Journal Debug Report

**Date:** 2026-02-27
**Status:** Root cause identified — config gate is correct but `daily_journal` is not set to `true` in the installed config, confirmed by absence of any journal output files

---

## Summary

The `write_journal_entry()` function and its call site in `main()` are correctly implemented. The logic to guard on `daily_journal: true` is present and correct. The feature does not appear to be malfunctioning in a code sense — it is silently disabled because the installed `~/.claude/knowledge.json` has `daily_journal: false` (the default from `knowledge.example.json`), and `daily_journal: true` has not actually been written to the installed config.

Evidence: The vault at `~/Documents/brain/` contains no `AI/Journal/` directory at all. Extraction has run successfully (Claude-Notes for the project exist dated 2026-02-27), so the hook and extractor are working — but no journal file has ever been created.

---

## Code Path: Config Read to File Write

### 1. Config loading (`resolve_config`, lines 84–87)

```python
def resolve_config(cwd: str) -> dict:
    global_cfg = load_global_config()      # reads ~/.claude/knowledge.json
    project_cfg = find_project_config(cwd) # reads .claude/knowledge.local.json if found
    return {**global_cfg, **project_cfg}   # project config overrides global
```

`daily_journal` lives only in the global config (`~/.claude/knowledge.json`). The project config at `/Users/dan/code/knowledge-graph/.claude/knowledge.local.json` only contains `project_name` and `vault_folder` — it does not set `daily_journal`.

The default in `knowledge.example.json` is:
```json
"daily_journal": false,
"journal_folder": "AI/Journal",
"journal_name": "%Y-%m-%d"
```

### 2. Feature flag read (`main()`, lines 596–597)

```python
config = resolve_config(args.cwd)
autofile_enabled = config.get("autofile", False)
journal_enabled = config.get("daily_journal", False)
```

`daily_journal` is read into `journal_enabled`. Default is `False`. If the key is absent from `~/.claude/knowledge.json`, the journal is silently disabled with no warning or log line.

### 3. Call site (`main()`, lines 640–642)

```python
if journal_enabled and written:
    project_name = config.get("project_name", Path(args.cwd).name)
    write_journal_entry(written, config, args.session_id, project_name, now)
```

Two conditions must be true:
1. `journal_enabled` is truthy (i.e., `daily_journal: true` in config)
2. `written` is non-empty (at least one beat was written in this run)

If `journal_enabled` is `False`, `write_journal_entry` is never called, and no log line appears. There is **no stderr output** when the journal is skipped — it fails silently.

### 4. `write_journal_entry()` implementation (lines 542–575)

```python
def write_journal_entry(written_paths: list[Path], config: dict, session_id: str,
                         project_name: str, now: datetime) -> None:
    journal_folder = config.get("journal_folder", "AI/Journal")
    journal_name_tpl = config.get("journal_name", "%Y-%m-%d")
    date_str = now.strftime(journal_name_tpl)

    vault = Path(config["vault_path"])
    journal_dir = vault / journal_folder
    journal_dir.mkdir(parents=True, exist_ok=True)
    journal_path = journal_dir / f"{date_str}.md"
    ...
    print(f"[extract_beats] Journal updated: {journal_path}", file=sys.stderr)
```

Path construction: `{vault_path}/{journal_folder}/{journal_name_tpl formatted date}.md`

With defaults: `~/Documents/brain/AI/Journal/2026-02-27.md`

The function creates the directory if it doesn't exist, so a missing `AI/Journal/` folder is not a blocker — it would be created on first run.

---

## Journal Entry Format

A newly created daily journal file looks like:

```markdown
---
type: journal
date: 2026-02-27
---

# 2026-02-27

## Session 14281578 — knowledge-graph

3 note(s) captured:
- [[Personal/Projects/knowledge-graph/Claude-Notes/Some Beat Title|Some Beat Title]]
- [[Personal/Projects/knowledge-graph/Claude-Notes/Another Beat|Another Beat]]
- [[AI/Claude-Sessions/General Insight|General Insight]]
```

On subsequent extractions the same day, a new `## Session <id8> — <project>` block is appended to the existing file. The session ID is truncated to 8 characters.

Wikilinks use vault-relative paths: `[[relative/path/to/file.md|stem]]` where `stem` is `path.stem` (filename without `.md`).

---

## What `daily_journal: true` Was Not Actually Set

### Evidence

1. **`AI/Journal/` does not exist in the vault.** The directory at `/Users/dan/Documents/brain/AI/Journal/` does not exist. If the journal had ever fired even once, this directory would have been created (the code calls `journal_dir.mkdir(parents=True, exist_ok=True)`).

2. **Beats have been written successfully.** Files exist in `/Users/dan/Documents/brain/Personal/Projects/knowledge-graph/Claude-Notes/` dated 2026-02-27, confirming the extractor has run, beats have been written (`written` list is non-empty), and the `if journal_enabled and written` branch was reached — but `journal_enabled` was `False`.

3. **No log line.** If the journal had run, stderr would contain `[extract_beats] Journal updated: ...`. The absence of that line in any prior run further confirms the branch was never entered.

4. **`~/.claude/knowledge.json` is inaccessible for direct inspection** in this session (permission denied), but the installer copies `knowledge.example.json` as the initial config, which has `daily_journal: false`. There is no mechanism in the installer or elsewhere that would flip it to `true` automatically.

---

## Diagnosis

The claim that `daily_journal: true` has been "enabled in config" appears to be incorrect, or the config was modified but then the installer was re-run (which would have left the existing `knowledge.json` unchanged since install.sh only copies the example if the config doesn't already exist).

The most likely scenario: the user set `daily_journal: true` in the *source repo's* `knowledge.example.json` or assumed it was set, but the actual value in `~/.claude/knowledge.json` remains `false`.

---

## Root Cause

**Primary:** `daily_journal` is not set to `true` in `~/.claude/knowledge.json`. The flag defaults to `false` and the journal is silently skipped with no log output.

**Secondary (contributing):** The code provides no feedback when journal is disabled. The only log line related to journal (`[extract_beats] Journal updated: ...`) only appears on success. There is no "journal skipped: daily_journal=false" message. This makes it easy to believe the feature is enabled when it is not.

---

## Specific Fix Required

### Immediate: Config change

Edit `~/.claude/knowledge.json` and set:

```json
{
  "daily_journal": true,
  "journal_folder": "AI/Journal",
  "journal_name": "%Y-%m-%d"
}
```

`journal_folder` and `journal_name` already have sensible defaults in the code (`"AI/Journal"` and `"%Y-%m-%d"` respectively), so only `daily_journal: true` is strictly required. The folder will be created automatically on first run.

### Optional: Code improvement — log when journal is skipped

In `main()`, add a debug log line so the journal status is visible:

```python
if journal_enabled and written:
    project_name = config.get("project_name", Path(args.cwd).name)
    write_journal_entry(written, config, args.session_id, project_name, now)
elif not journal_enabled:
    print("[extract_beats] Daily journal disabled (daily_journal=false in config)", file=sys.stderr)
```

This would make the config state visible in hook output and prevent future confusion. The change is in `main()` at lines 640–642 of `/Users/dan/code/knowledge-graph/extractors/extract_beats.py`.

---

## Verification Steps After Fix

1. Set `daily_journal: true` in `~/.claude/knowledge.json`
2. Run the extractor manually against any transcript:
   ```bash
   python3 /Users/dan/code/knowledge-graph/extractors/extract_beats.py \
     --transcript <path-to-any-jsonl> \
     --session-id test-journal-verify \
     --trigger manual \
     --cwd /Users/dan/code/knowledge-graph 2>&1 | grep -i journal
   ```
3. Expected output: `[extract_beats] Journal updated: /Users/dan/Documents/brain/AI/Journal/2026-02-27.md`
4. Verify the file exists at `~/Documents/brain/AI/Journal/2026-02-27.md`
5. Alternatively use `--beats-json` with a pre-made beats file to skip the LLM call:
   ```bash
   echo '[{"type":"insight","scope":"general","title":"Test","summary":"test","tags":["test"],"body":"test body"}]' > /tmp/test-beats.json
   python3 /Users/dan/code/knowledge-graph/extractors/extract_beats.py \
     --beats-json /tmp/test-beats.json \
     --session-id test-journal-verify \
     --trigger manual \
     --cwd /Users/dan/code/knowledge-graph 2>&1
   ```

---

## MCP Server Note

The MCP server (`mcp/server.py`) handles journal correctly in its `kg_extract` tool (lines 120–122):

```python
if config.get("daily_journal", False) and written:
    project = config.get("project_name", project_name or "unknown")
    write_journal_entry(written, config, session_id, project, now)
```

Same pattern, same behavior. The config fix above will enable it in both code paths simultaneously.
