# Policies: Capture

## P-1: Zero-action capture after setup
Automatic extraction fires on PreCompact and SessionEnd hooks without any user action — the hook invocation, LLM call, and vault write happen invisibly.
- **Derived from**: GP-1 (Zero Ceremony for the Common Case)
- **Established**: planning phase
- **Status**: active

## P-2: All vault writes go through vault.py
`vault.write_beat()` is the single write path for beat creation. MCP tools and hooks both converge here; no caller writes vault markdown directly.
- **Derived from**: GP-2 (The Vault is the Canonical Store) + Constraint C6
- **Established**: planning phase
- **Status**: active (note: curation tools — enrich, review, restructure — write via other paths; this policy applies to beat creation only)

## P-3: Hooks always exit 0
Hook scripts must never block the parent Claude Code session. All errors are caught, logged, and swallowed. `set -euo pipefail` is not used.
- **Derived from**: GP-8 (Graceful Degradation Over Hard Failure) + Constraint C7
- **Established**: planning phase
- **Status**: active

## P-4: Session-level deduplication
Each Claude Code session ID is processed at most once. The dedup log (`cb-extract.log`) is checked before extraction begins; the SessionEnd hook checks it to avoid double-processing if PreCompact already ran.
- **Derived from**: Constraint C11
- **Established**: planning phase
- **Status**: active

## P-5: Subprocess environment isolation
When spawning `claude -p`, five env vars are stripped (`CLAUDECODE`, `CLAUDE_CODE_ENTRYPOINT`, `CLAUDE_CODE_DISABLE_FEEDBACK_SURVEY`, `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`, `CLAUDE_CODE_SESSION_ACCESS_TOKEN`) and the subprocess runs from `~/.claude/cyberbrain/` (no CLAUDE.md) to prevent hangs and config injection.
- **Derived from**: Constraint C8, C9
- **Established**: planning phase
- **Status**: active

## P-6: Beat type vocabulary is vault-owned
The set of valid beat types is read from the vault's `CLAUDE.md`, not hardcoded in the extractor. This keeps the system vault-adaptive rather than vault-prescriptive.
- **Derived from**: GP-5 (Vault-Adaptive, Not Vault-Prescriptive)
- **Established**: planning phase
- **Status**: active
