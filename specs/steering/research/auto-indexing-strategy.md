# Research: Auto-Indexing Strategy

## Current State

### What the index does

The cyberbrain search index is a SQLite database (`~/.claude/cyberbrain/search-index.db`) that powers `cb_recall`. It supports three backends: `grep` (no index), `fts5` (BM25 full-text search), and `hybrid` (FTS5 + usearch HNSW semantic vectors). The FTS5 and hybrid backends store per-note rows with title, summary, tags, body, content hash, and optionally an embedding vector.

### When the index stays current

The index updates incrementally in these cases:

1. **Beat extraction** (PreCompact/SessionEnd hooks, `cb_extract`, `cb_file`): `vault.write_beat()` and `autofile.autofile_beat()` call `search_index.update_search_index()` after each note write.
2. **MCP curation tools** (`cb_restructure`, `cb_review`, `cb_enrich`): These call `_index_paths()` for written/modified notes and `_prune_index()` to remove deleted entries.

### When the index becomes stale

The index does NOT update when:

1. **User edits notes in Obsidian.** Title, tags, summary, or body changes are invisible to the index until a manual `cb_reindex`.
2. **User creates notes manually in Obsidian.** New notes are not indexed.
3. **User moves or renames notes in Obsidian.** The old path remains in the index (stale entry); the new path is missing.
4. **User deletes notes in Obsidian.** Stale entries remain until pruned.
5. **External sync tools (Obsidian Sync, iCloud, git) add/modify/delete notes.** Same as manual edits.

### How staleness manifests

- **Missing results:** Notes created or significantly edited outside cyberbrain don't appear in `cb_recall` searches.
- **Wrong results:** Stale entries point to deleted or moved files. `cb_recall` may return cards for notes that no longer exist or whose content has changed.
- **Misleading synthesis:** If `cb_recall` uses LLM synthesis, stale snippets are injected as context, potentially misleading the model.

### Current remediation

The only fix today is manual: the user must invoke `cb_reindex(prune=True)` to remove stale entries, or `cb_reindex(rebuild=True)` for a full rebuild. There is no scheduled or automatic trigger.

### Performance characteristics

- **Prune**: Fast. Reads all `(id, path)` rows from the `notes` table, checks each path on disk, deletes missing ones. O(n) where n = indexed notes. For a 2K-note vault, this takes under 1 second.
- **Full rebuild (FTS5)**: Reads and parses frontmatter from every `.md` file in the vault via `rglob("*.md")`. Content-hash dedup skips unchanged notes. For a 2K-note vault, expect 5-15 seconds.
- **Full rebuild (hybrid)**: FTS5 rebuild plus embedding generation for every note. Embedding with `bge-micro-v2` is ~1ms/note on CPU, so a 2K-note vault adds ~2 seconds. Smart Connections import can skip embedding entirely if the model matches.

### Bug noted

`cb_reindex(rebuild=True)` checks `hasattr(backend, "build_full_index")`, but no backend defines that method — `build_full_index` is a module-level function in `search_index.py`, not a method on the backend object. Because the `hasattr` check silently evaluates to `False` for every backend, the rebuild path always returns "Active search backend does not support full rebuild." and never rebuilds anything. The correct fix is to replace the `hasattr` guard and the `backend.build_full_index(config)` call with a direct call to the module-level `search_index.build_full_index(config)`, which internally calls `backend.build_index()`. This is a pre-existing bug unrelated to this research but worth fixing.

---

## Options Evaluated

### Option 1: SessionEnd Hook

**How it works:** Add a reindex step to the existing `session-end-extract.sh` hook (or create a separate `session-end-reindex.sh`). After extraction completes (or in parallel), run a prune + incremental index update.

**Pros:**
- Uses existing hook infrastructure — `hooks/hooks.json` already registers `SessionEnd`.
- No new processes or daemons. Runs only when a Claude Code session ends.
- Detached execution (`nohup &`) means it doesn't block session exit.
- Aligns with the "no persistent daemon" constraint.
- Covers the most common staleness scenario: user works in Obsidian between sessions, then starts a new Claude Code session.

**Cons:**
- Only fires when a Claude Code session ends. If the user edits notes in Obsidian and then uses Claude Desktop (MCP), the index won't have been refreshed.
- Does not cover long-running sessions where the user edits notes in Obsidian mid-session.
- Adds latency to session end (though detached, so non-blocking).
- The index is updated *after* the session, not *before* the next one. The user's next `cb_recall` in a new session could still hit a stale index if the reindex hasn't finished yet.

**Failure modes:**
- Vault not mounted (external drive, cloud sync not ready): Script should check vault path exists before proceeding. Already standard in hook scripts.
- Index lock contention: SQLite handles concurrent writes via WAL journal. If extraction and reindex run simultaneously, SQLite serializes them. No corruption risk, minor latency.
- Script crash: `exit 0` invariant means it never blocks the session.

### Option 2: Lazy Reindex on First `cb_recall`

**How it works:** When `cb_recall` is invoked and the index is older than a threshold (e.g., 1 hour since last full scan), run a fast incremental update before returning results. Check the index's last-modified timestamp against vault files' mtimes.

**Pros:**
- Detects staleness at query time and updates before returning results — the index is refreshed exactly when it matters most.
- No background processes, no daemons, no cron.
- Self-correcting: stale index is fixed exactly when staleness would cause a problem.
- Works for both Claude Code and Claude Desktop.

**Cons:**
- Adds latency to the first `cb_recall` after vault changes. A full scan of mtimes for 2K files takes <100ms; actual re-indexing of changed files depends on how many changed.
- Requires tracking "last scan time" (a single timestamp file or SQLite pragma).
- The default 1-hour threshold means changes made within the last hour may not be caught — results can still be stale within that window. This is a reasonable trade-off (not a freshness guarantee), and the threshold is configurable.
- Does not help if the user never calls `cb_recall` (edge case — if they don't search, staleness doesn't matter).

**Failure modes:**
- Large number of changed files (e.g., after a git merge or Obsidian Sync bulk update): Could add noticeable latency to the first recall. Mitigated by the content-hash skip in `index_note()`.
- Vault not mounted: Same as Option 1 — check before scanning.

### Option 3: Cron Job

**How it works:** Install a cron job (or launchd plist on macOS) that runs `cyberbrain-reindex` every N minutes.

**Pros:**
- Completely independent of Claude Code session lifecycle.
- Index is always relatively fresh regardless of which interface the user uses.
- Simple to understand and debug.

**Cons:**
- Requires a `cyberbrain-reindex` CLI entry point (does not exist today — needs adding to `pyproject.toml`).
- Runs even when the user isn't using cyberbrain, wasting CPU cycles.
- Cron job installation is another setup step — must be added to `install.sh` and the plugin system.
- On macOS, cron is discouraged in favor of launchd; cross-platform support adds complexity.
- If the vault is on an external drive that's sometimes unmounted, the cron job fails silently every run until mounted.
- Adds a maintenance burden: install, uninstall, frequency tuning, log rotation.

**If chosen — concrete spec:**
- Cron expression: `*/15 * * * * /path/to/cyberbrain-reindex --prune --incremental 2>>$HOME/.claude/cyberbrain/logs/cb-reindex-cron.log`
- Install: `(crontab -l 2>/dev/null; echo "*/15 * * * * ...") | crontab -`
- Uninstall: `crontab -l | grep -v cyberbrain-reindex | crontab -`

### Option 4: File System Watcher (FSEvents / inotify)

**How it works:** A background daemon watches the vault directory for file changes and triggers incremental indexing in real-time.

**Pros:**
- Near-instant index freshness.
- Handles all change sources (Obsidian, sync, manual edits).

**Cons:**
- **Requires a persistent daemon** — directly violates the "no persistent daemon" guiding principle (Principle 6: "Flat files over daemons").
- Adds a dependency (watchdog or similar library).
- Must handle daemon lifecycle: start, stop, crash recovery, startup registration.
- FSEvents on macOS can batch events with variable delay.
- If the vault is on a network mount, FS watchers may not work reliably.

**Verdict:** Rejected per guiding principles. The complexity-to-benefit ratio is poor for this use case.

---

## Recommendation

**Primary: Option 2 — Lazy Reindex on First `cb_recall`** (with Option 1 as a complement).

### Rationale

1. **Fixes staleness at the moment it matters.** The only time a stale index causes a user-visible problem is when `cb_recall` returns wrong results. Detecting and refreshing at recall time catches most staleness; the 1-hour default threshold means very recent changes (within the last hour) may still be stale, but this is a configurable trade-off, not a silent failure.

2. **Zero ceremony.** No cron jobs to install, no hooks to maintain, no background processes. Aligns perfectly with Principle 1 (Zero Ceremony) and Principle 6 (Lean Architecture).

3. **Works for all interfaces.** Claude Code, Claude Desktop, and any future MCP client all go through `cb_recall`. The fix is at the point of use, not at a platform-specific lifecycle event.

4. **Fast enough.** Scanning mtimes for 2K-10K files takes <100ms. Re-indexing only changed files (content-hash dedup) keeps the actual indexing work proportional to changes, not vault size.

5. **Self-correcting.** No failure mode where the index silently stays stale for days. If the user searches, the index refreshes.

**Complement: Option 1 (SessionEnd hook)** as a best-effort optimization. Adding a prune + incremental reindex to the SessionEnd hook means the index is usually fresh by the time the next session starts. This is not load-bearing — Option 2 catches anything the hook misses — but it reduces first-recall latency in the common case.

---

## Implementation Spec

### Part A: Lazy Reindex in `cb_recall` (primary)

**Location:** `src/cyberbrain/mcp/tools/recall.py`, with supporting function in `src/cyberbrain/extractors/search_index.py`.

**Mechanism:**

1. Add a `last_scan_ts` file at `~/.claude/cyberbrain/.index-scan-ts` containing a single Unix timestamp (seconds).
2. In `search_index.py`, add a function:

```python
def incremental_refresh(config: dict, max_age_seconds: int = 3600) -> int:
    """
    If the last scan is older than max_age_seconds, walk the vault and
    re-index files whose mtime is newer than last_scan_ts.
    Returns the number of notes re-indexed, or -1 if skipped.
    """
```

3. The function:
   - Reads `last_scan_ts` from the marker file. If missing or older than `max_age_seconds`, proceeds.
   - **First-run behavior:** If the marker file does not exist, `last_scan_ts` is treated as 0 (epoch). Every vault file has `mtime > 0`, so all notes are indexed on first run. The marker file is created at the end of the run. This bootstraps the index automatically with no special-case logic.
   - Walks the vault with `Path(vault).rglob("*.md")`.
   - For each file with `mtime > last_scan_ts`, calls `backend.index_note()`.
   - Calls `backend.prune_stale_notes()` once at the end.
   - Writes current timestamp to the marker file.
   - Returns count of re-indexed notes.

4. In `recall.py`, before executing the search query, call `incremental_refresh(config)`. This adds negligible latency when the index is fresh (one file stat + timestamp comparison).

**Threshold:** Default 3600 seconds (1 hour). Configurable via `config["index_refresh_interval"]` for users who want more or less aggressive refresh.

**Error handling:**
- All exceptions caught and logged. A failed refresh never blocks the search — it falls through to searching the existing (possibly stale) index.
- If vault path doesn't exist, skip silently (vault not mounted).
- If SQLite is locked (concurrent write), retry once after 100ms, then skip.

**Implementation dependency:** Part A must be implemented before Part B. The SessionEnd hook in Part B calls the same `incremental_refresh` function introduced in Part A. Part B is a thin shell wrapper that invokes Part A's logic at session end; it has no independent code path.

### Part B: SessionEnd Hook Reindex (complement)

**Location:** `hooks/session-end-extract.sh` (append to existing script).

**Mechanism:** After the extraction subprocess is launched (or if extraction is skipped due to dedup), run a lightweight reindex:

```bash
# Reindex: prune stale entries and refresh recently modified notes
if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ]; then
  nohup uv run --directory "$CLAUDE_PLUGIN_ROOT" \
    python -m cyberbrain.extractors.search_index \
    >> "$SESSION_END_LOG" 2>&1 &
elif command -v cyberbrain-reindex >/dev/null 2>&1; then
  nohup cyberbrain-reindex >> "$SESSION_END_LOG" 2>&1 &
fi
```

**Requires:** Add `cyberbrain-reindex` entry point to `pyproject.toml`:

```toml
[project.scripts]
cyberbrain-reindex = "cyberbrain.extractors.search_index:main"
```

And update `search_index.py`'s `__main__` block to call `incremental_refresh(config)` instead of `build_full_index(config)`.

**No changes to `hooks/hooks.json`** — the SessionEnd hook is already registered.

**Error handling:** Same as existing hook: no `set -euo pipefail`, always `exit 0`, output to log file.

### Part C: Bug Fix (while here)

`reindex.py` checks `hasattr(backend, "build_full_index")` before proceeding with a full rebuild, but no backend object defines a `build_full_index` method — that name belongs to the module-level function in `search_index.py`. The `hasattr` check therefore always returns `False`, and every call to `cb_reindex(rebuild=True)` silently returns "Active search backend does not support full rebuild." without ever rebuilding the index.

Fix: remove the `hasattr` guard and replace the `backend.build_full_index(config)` call with `search_index.build_full_index(config)` (the module-level function), which internally calls `backend.build_index()` with proper error handling and logging already in place.

---

## Incremental Indexing Assessment

### Current state

The FTS5 backend already supports content-hash dedup: `index_note()` checks if the note's content hash matches the stored hash and skips if unchanged. This means `build_index()` is already semi-incremental — it walks all files but only re-indexes changed ones.

### What's missing for true incremental

True incremental indexing (only visit files that changed) requires knowing which files changed since the last scan. Two approaches:

**Approach A: mtime comparison (recommended)**
- Store a "last full scan" timestamp.
- On refresh, only visit files with `mtime > last_scan_ts`.
- Fast: `os.stat()` is cheap; `Path.rglob("*.md")` with stat filtering on a 2K-file vault takes <100ms.
- Handles: edits, new files. Does NOT detect deletions (files that disappeared have no mtime to check).
- Solution for deletions: run `prune_stale_notes()` on each refresh (reads all indexed paths, checks existence). This is O(indexed_notes) but involves no file reads, just `Path.exists()` checks.

**Approach B: SQLite-tracked file manifest**
- Store `(path, mtime, content_hash)` for every vault file in a manifest table.
- On refresh, compare manifest against filesystem.
- More precise but adds complexity. The mtime approach is sufficient for the vault scale.

### Recommendation

Implement **Approach A** (mtime comparison + prune). It is simple, fast, and sufficient for vaults up to 10K notes. The combination of mtime-filtered indexing and path-existence pruning covers all staleness scenarios:

| Change type | Detected by |
|---|---|
| Note edited | mtime > last_scan_ts |
| Note created | mtime > last_scan_ts |
| Note moved | prune (old path gone) + mtime (new path is "new") |
| Note deleted | prune (path gone) |
| Note renamed | prune (old path gone) + mtime (new path is "new") |

Full rebuild (`cb_reindex(rebuild=True)`) remains available as a fallback for edge cases or corrupted indexes.

### Is it worth implementing?

Yes. The incremental refresh function is ~30 lines of code, adds <100ms latency to the first `cb_recall` after a quiet period, and eliminates the most common source of user confusion ("why didn't cb_recall find my note?"). The cost-to-benefit ratio is excellent.
