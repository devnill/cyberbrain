# SP7: Session-End Capture — Research Output

**Spike:** SP7 — Sessions ending without `/compact` are never captured.
**Date:** 2026-02-27
**Status:** Complete

---

## Finding 1 — Claude Code Hook System Map

Source: https://code.claude.com/docs/en/hooks (official reference, fetched 2026-02-27)

Claude Code supports 17 hook lifecycle events. The full list, ordered by session lifecycle:

| Event | When it fires | Can block? |
|---|---|---|
| `SessionStart` | When a session begins or resumes | No |
| `UserPromptSubmit` | When a prompt is submitted, before processing | Yes |
| `PreToolUse` | Before a tool call executes | Yes |
| `PermissionRequest` | When a permission dialog appears | Yes |
| `PostToolUse` | After a tool call succeeds | No |
| `PostToolUseFailure` | After a tool call fails | No |
| `Notification` | When Claude Code sends a notification | No |
| `SubagentStart` | When a subagent is spawned | No |
| `SubagentStop` | When a subagent finishes | Yes |
| `Stop` | When Claude finishes responding | Yes |
| `TeammateIdle` | When an agent team teammate goes idle | Yes |
| `TaskCompleted` | When a task is marked completed | Yes |
| `ConfigChange` | When a config file changes during a session | Yes |
| `WorktreeCreate` | When a worktree is being created | Yes |
| `WorktreeRemove` | When a worktree is being removed | No |
| `PreCompact` | Before context compaction | No |
| `SessionEnd` | **When a session terminates** | No |

### SessionEnd — the key hook for SP7

`SessionEnd` fires when a Claude Code session ends. It is purpose-built for cleanup
tasks, logging session statistics, and saving session state. It is not blockable — it
cannot prevent session termination, only react to it.

**Stdin payload:**
```json
{
  "session_id": "00893aaf-19fa-41d2-8238-13269b9b3ca0",
  "transcript_path": "/Users/dan/.claude/projects/-Users-dan-code-my-project/00893aaf-19fa-41d2-8238-13269b9b3ca0.jsonl",
  "cwd": "/Users/dan/code/my-project",
  "permission_mode": "default",
  "hook_event_name": "SessionEnd",
  "reason": "other"
}
```

The payload is identical in structure to the `PreCompact` hook payload — it includes
`transcript_path`, `session_id`, and `cwd`. The existing `pre-compact-extract.sh` hook
reads exactly these fields from stdin. Adapting it for `SessionEnd` requires almost no
change.

**The `reason` field** indicates why the session ended:

| Reason value | When it applies |
|---|---|
| `clear` | User ran `/clear` |
| `logout` | User explicitly logged out |
| `prompt_input_exit` | User exited at the prompt input (e.g., Ctrl+C, `exit`) |
| `bypass_permissions_disabled` | Bypass permissions mode was disabled |
| `other` | All other exit reasons (terminal close, timeout, etc.) |

This is significant: a normal terminal close (closing the window), a session timeout,
and a CLI crash all appear to fall into `other`. The `SessionEnd` hook therefore fires
on both graceful exits and the soft-exits that currently go uncaptured.

**Important caveat:** Whether `SessionEnd` fires on hard kills (SIGKILL, `kill -9`,
force-closing the terminal from the OS level) is not documented. The docs say it fires
"when a session terminates" — this likely implies a process-controlled teardown, not an
OS-level process kill. Sessions killed with SIGKILL almost certainly do not trigger it.
This is a known gap that cannot be resolved from documentation alone; it requires
empirical testing.

**Hook type constraint:** `SessionEnd` only supports `type: "command"` hooks — not prompt
or agent hooks. This matches the current `pre-compact-extract.sh` implementation.

**Matcher support:** `SessionEnd` supports matchers on the `reason` field. You can write
a hook that only fires for `other|logout|prompt_input_exit` (skipping `clear` and
`compact`, which are already handled by `PreCompact`).

### Current hook registration

`hooks/hooks.json` in the project:
```json
{
  "hooks": {
    "PreCompact": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/pre-compact-extract.sh",
            "timeout": 120,
            "statusMessage": "Extracting knowledge before compaction..."
          }
        ]
      }
    ]
  }
}
```

`install.sh` registers this same hook in `~/.claude/settings.json` under the
`PreCompact` key. Adding a `SessionEnd` hook requires adding a parallel entry.

---

## Finding 2 — Transcript File Lifecycle

### Where transcripts live

Claude Code stores transcripts at:
```
~/.claude/projects/<encoded-cwd>/<session-id>.jsonl
```

The `<encoded-cwd>` is the working directory with `/` replaced by `-`, starting with a
leading `-`. For example, `/Users/dan/code/my-app` encodes to `-Users-dan-code-my-app`.

The `<session-id>` is a UUID (e.g., `00893aaf-19fa-41d2-8238-13269b9b3ca0`).

The `transcript_path` field in every hook's stdin payload points directly to this file.
The `kg-extract` skill's Step 1 also documents this path convention and uses it to
find the current session's transcript by picking the most recently modified `.jsonl`
file in the project directory.

### Persistence after session end

The transcripts are plain JSONL append-only logs. Based on how the system works:

- They are **not automatically deleted** after a session ends — the `kg-extract` skill
  documents backfilling from old transcripts as a supported use case, which only works
  if they persist.
- The `import-desktop-export.py` script uses a persistent state file at
  `~/.claude/kg-import-state.json` to track which sessions have been processed — this
  design would be unnecessary if transcripts were ephemeral.
- After a normal session exit (no compact), the transcript file remains on disk,
  readable, containing the full session conversation.

### After compaction

When `/compact` fires, the `PreCompact` hook runs first (before the transcript is
truncated). After compaction, the session continues with a truncated context. The
transcript file likely reflects the post-compact state in subsequent entries, but the
pre-compact content has already been extracted by the hook. There is no evidence in the
codebase that the original transcript file is deleted or overwritten by compaction —
compaction affects the in-memory context, not the on-disk log.

### Deduplication gap

There is currently **no deduplication mechanism** in the hook path. The
`extract_beats.py` extractor has no state file — it writes beats unconditionally on
every invocation. The `import-desktop-export.py` script has a state file
(`kg-import-state.json`) that tracks processed conversation UUIDs, but this is
separate from the hook path and uses Claude Desktop's conversation UUIDs, not
Claude Code session IDs.

This means: if both `PreCompact` and `SessionEnd` hooks are registered, a session that
does use `/compact` will have its transcript processed twice — once by `PreCompact`
before compaction, and again by `SessionEnd` when the session finally ends.
Deduplication must be addressed as part of any `SessionEnd` hook implementation.

---

## Finding 3 — Approaches Evaluated

### Option A: SessionEnd Hook (Recommended)

**Mechanism:** Register a `SessionEnd` hook alongside the existing `PreCompact` hook.
The hook fires when any session terminates — whether the user ran `/compact`, typed
`exit`, closed the terminal, or let it time out. It receives `transcript_path`,
`session_id`, and `cwd` in the same format as `PreCompact`.

**What it covers:**
- User closes the terminal window (reason: `other`)
- Session times out (reason: `other`)
- User explicitly exits (reason: `prompt_input_exit`)
- User runs `/clear` — could be excluded via matcher if desired (reason: `clear`)

**What it misses:**
- Hard kills (SIGKILL) — the process doesn't get a chance to run teardown hooks
- Probably rare in practice compared to normal closes and timeouts

**Deduplication requirement:** Sessions that do use `/compact` will trigger both
`PreCompact` and `SessionEnd`. A state file at `~/.claude/kg-session-state.json`
tracking processed session IDs by `session_id` would prevent double extraction. The
`SessionEnd` hook checks: "has this session_id already been processed by PreCompact?"
If yes, skip. If no, run extraction.

**Implementation sketch:**

1. Add a state file writer to `pre-compact-extract.sh`: after successful extraction,
   record `{session_id: true}` to `~/.claude/kg-session-state.json`.

2. Create `hooks/session-end-extract.sh`: same logic as `pre-compact-extract.sh`, but
   before calling the extractor, check if `session_id` is already in the state file.
   If it is, exit 0 (already captured). If not, run extraction and record the session.

3. Register the new hook in `hooks.json` and `install.sh`:
   ```json
   "SessionEnd": [
     {
       "matcher": "other|logout|prompt_input_exit",
       "hooks": [
         {
           "type": "command",
           "command": "~/.claude/hooks/session-end-extract.sh",
           "timeout": 120
         }
       ]
     }
   ]
   ```
   The matcher `other|logout|prompt_input_exit` skips `clear` (user cleared context,
   not ending a work session) and `bypass_permissions_disabled` (irrelevant).
   Whether to include or exclude `clear` is a product decision.

**Pros:**
- Built into Claude Code's lifecycle — no external process needed
- Same transcript path, same extraction logic — minimal new code
- Fires reliably for all graceful and semi-graceful exits
- No polling, no file system watcher, no cron job

**Cons:**
- Does not capture hard kills (SIGKILL, kill -9)
- Requires deduplication to avoid double-extracting sessions that also compact
- Unknown whether it fires after the terminal window closes but before the process exits
  (needs empirical verification)
- A session that crashes mid-response might not trigger it

**Verdict:** This is the right first approach. It solves the common cases (terminal
close, timeout, explicit exit) with minimal added complexity.

---

### Option B: Cron Job / Scheduled Scan

**Mechanism:** A script runs on a schedule (e.g., every 15 minutes via `launchd` on
macOS). It scans `~/.claude/projects/**/*.jsonl` for transcript files that are newer
than the last run or not in the state file, and runs extraction on them.

**State tracking:** A state file records processed `{transcript_path: processed_at}`
entries. "Unprocessed" means: the file exists, has user/assistant turns, and its path
is not in the state file.

**Pros:**
- Captures everything, including hard-killed sessions (SIGKILL), since it reads the
  transcript file regardless of how the session ended
- Works even if Claude Code's hook system has gaps
- Straightforward to implement without modifying hook registration

**Cons:**
- Latency: a session that ends at 10:00 might not be extracted until 10:15
- Requires `launchd` or `cron` setup — non-trivial for users not familiar with macOS
  scheduling
- Cron jobs are hard to package in `install.sh` without root or user intervention
- Harder to reason about when extraction happened relative to the session
- Polling approach: runs even when nothing has changed

**Verdict:** Useful as a fallback mechanism to catch hard-killed sessions that `SessionEnd`
misses. Not the primary approach — too much friction to install and too much latency.

---

### Option C: File System Watcher

**Mechanism:** A background process (e.g., using `fswatch` on macOS) watches
`~/.claude/projects/` for JSONL file modifications. When a JSONL file hasn't been
modified for N minutes (e.g., 5 minutes), it's assumed the session has ended and
extraction is triggered.

**Pros:**
- Lower latency than cron for detecting session end
- Catches sessions regardless of exit type
- No changes to Claude Code hook configuration required

**Cons:**
- `fswatch` is not installed by default on macOS — requires Homebrew
- A background daemon needs to be managed (started on login, kept alive, stopped
  cleanly) — significantly more operational complexity than a hook
- The "N minutes of inactivity = session ended" heuristic is fragile: long pauses in
  a session would trigger false extractions
- On a machine running multiple concurrent Claude Code sessions, the watcher would need
  to distinguish between sessions
- Hard to package in `install.sh` — daemon management varies across OS versions

**Verdict:** Over-engineered for the problem. The `SessionEnd` hook solves the same
problem with native support. File watching would only be justified if Claude Code had
no hook for session end, which it does.

---

### Option D: Manual `/kg-extract` at Session End

**Mechanism:** No automation. The user runs `/kg-extract` before closing a session they
care about.

**Pros:**
- Already implemented — the `/kg-extract` skill exists
- Zero additional infrastructure
- User controls which sessions are captured (low signal-to-noise)

**Cons:**
- Requires user discipline — exactly the problem to be solved
- Sessions that end unexpectedly (crash, disconnect) are still missed
- Cognitive overhead: the user must remember to do it

**Verdict:** This already exists and is fine for intentional mid-session capture. It
does not solve the problem of unintentionally uncaptured sessions. Keep it; don't rely
on it as the primary solution.

---

## Ranked Recommendations

**1. Implement a `SessionEnd` hook (high priority, low effort)**

This is the right primary solution. It requires:
- A new `hooks/session-end-extract.sh` (~20 lines, nearly identical to
  `pre-compact-extract.sh`)
- A lightweight state file (`~/.claude/kg-session-state.json`) written by both hooks
  to prevent double-extraction
- Updating `hooks/hooks.json` and `install.sh` to register the new hook
- A new `--trigger session-end` value in `extract_beats.py` (or reuse `auto`)

The deduplication state file should use session IDs as keys and store minimal
metadata (timestamp of extraction, trigger that captured it). This also lays
groundwork for SP8 (deduplication strategy) for the hook path.

**2. Add a cron/launchd fallback for hard-killed sessions (lower priority)**

A simple script that scans for unprocessed transcripts using the same state file
as the `SessionEnd` hook. Run via `launchd` once per day (e.g., on login). This
catches the edge case of SIGKILL and any other scenario where `SessionEnd` doesn't
fire. The state file shared with the `SessionEnd` hook prevents double processing.

This can be a post-MVP addition once the `SessionEnd` hook is proven to work.

**3. Do not implement a file system watcher**

The operational complexity (daemon management, `fswatch` dependency, heuristic
timeout detection) is not justified when a first-class hook exists.

---

## Open Questions

1. **Does `SessionEnd` fire when the terminal window is force-closed?** The docs say
   it fires "when a session terminates" — this needs empirical verification. If the
   terminal emulator sends SIGTERM (normal) rather than SIGKILL (force), the hook
   should fire. Most terminal emulators send SIGTERM on window close.

2. **Is the transcript fully written/flushed when `SessionEnd` fires?** Almost
   certainly yes — the JSONL log is append-only and each line is flushed on write —
   but this should be verified with a test session.

3. **What is the `reason` for a session that ends after compaction?** If the user runs
   `/compact` and then closes the terminal, `SessionEnd` fires with some reason. The
   `PreCompact` hook will have already captured the session. The state file deduplication
   handles this, but the `reason` value for this case is worth knowing.

4. **Should `clear` sessions be captured?** `/clear` erases context but the session
   continues. The `SessionEnd` reason `clear` fires when the user runs `/clear`. This
   is likely not a session end in the productive-work sense. Recommend excluding `clear`
   from the matcher.

5. **Hook timeout:** The current `PreCompact` hook has a 120-second timeout. The
   `SessionEnd` hook should probably use the same or shorter timeout — the session is
   already ending and the user may have closed the terminal, so feedback is not visible.
   Extraction still runs to completion regardless.

---

## Implementation Checklist

When implementing this spike's recommendation:

- [ ] Add `session-end-extract.sh` to `hooks/` — adapts `pre-compact-extract.sh`
      with a deduplication check before calling the extractor
- [ ] Define the state file format: `~/.claude/kg-session-state.json` with
      `{session_id: {captured_at, trigger}}` entries
- [ ] Modify `pre-compact-extract.sh` to write to the state file after successful extraction
- [ ] Update `hooks/hooks.json` to register `SessionEnd` with matcher
      `other|logout|prompt_input_exit`
- [ ] Update `install.sh` to register the `SessionEnd` hook in `~/.claude/settings.json`
- [ ] Consider a `--trigger session-end` value to distinguish session-end extractions
      in beat frontmatter (currently only `auto` and `manual` exist)
- [ ] Write a test procedure: start a session, do some work, close the terminal,
      verify beats appear in the vault within 2 minutes
- [ ] Verify that a session that used `/compact` is not extracted twice
