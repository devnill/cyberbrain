# Module: Hooks

## Scope

Bash hooks that connect Claude Code session lifecycle events to the extraction pipeline. Two hooks: PreCompact (synchronous, before memory compaction) and SessionEnd (detached, after session closes).

NOT responsible for: extraction logic (extraction module), vault writing (vault module). The hooks are thin wrappers that parse hook context JSON and invoke the Python extractor.

## Provides

- `pre-compact-extract.sh` — Reads hook context JSON from stdin; parses `transcript_path`, `session_id`, `trigger`, `cwd`; invokes `extract_beats.py` synchronously.
- `session-end-extract.sh` — Same parsing; checks dedup log to skip already-extracted sessions; invokes `extract_beats.py` detached via `nohup ... &` so extraction survives session close.
- `hooks.json` — Claude Code hook registration file. Registers both hooks with 120s timeout.

## Requires

- `src/cyberbrain/extractors/extract_beats.py` (from: extraction) — The Python extractor CLI. Invoked via `uv run --directory $CLAUDE_PLUGIN_ROOT python -m cyberbrain.extractors.extract_beats` in plugin mode, or via the `cyberbrain-extract` entry point.
- `python3` on PATH — For both JSON parsing (inline) and extractor invocation.
- `~/.claude/logs/cb-extract.log` (from: vault/run_log) — Dedup log checked by SessionEnd hook.

## Boundary Rules

- **Always exit 0.** A non-zero exit from PreCompact blocks compaction; from SessionEnd may cause undefined behavior. All error paths print to stderr and `exit 0`.
- **No `set -euo pipefail`.** Error handling is explicit per-command with `if` guards.
- JSON parsing uses inline `python3 -c` with `2>/dev/null` — parse failure is a silent skip.
- `$CLAUDE_PLUGIN_ROOT` takes precedence over `~/.claude/cyberbrain/` for extractor location.
- SessionEnd runs detached: `nohup ... &` with output to `~/.claude/logs/cb-session-end.log`.
- SessionEnd pre-flight dedup check uses `grep -qF` on the extract log — fast shell-level check before spawning Python.

## Internal Design Notes

- Files: `hooks/pre-compact-extract.sh` (50 lines), `hooks/session-end-extract.sh` (68 lines), `hooks/hooks.json`
- `eval "$PARSE_OUT"` sets shell variables from Python's `shlex.quote`-safe output
- PreCompact hook output goes to stdout/stderr (visible in Claude Code); SessionEnd goes to log file
- `setsid` is not used (macOS-incompatible); `nohup ... &` achieves process detachment
