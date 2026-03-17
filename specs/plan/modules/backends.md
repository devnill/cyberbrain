# Module: Backends

## Scope

LLM backend implementations. Provides a uniform `call_model()` interface that dispatches to one of three backends: `claude-code` (subprocess), `bedrock` (Anthropic SDK), `ollama` (HTTP). Handles subprocess environment sanitization for nested Claude sessions.

NOT responsible for: prompt loading, response parsing, beat extraction logic.

## Provides

- `call_model(system_prompt: str, user_message: str, config: dict) -> str` — Dispatches to the appropriate backend based on `config["backend"]`. Returns raw LLM response text. Raises `BackendError` on any failure.
- `_call_claude_code(system_prompt, user_message, config) -> str` — claude-code backend (exported for direct use by MCP recall synthesis).
- `_call_bedrock(system_prompt, user_message, config) -> str` — Bedrock backend.
- `_call_ollama(system_prompt, user_message, config) -> str` — Ollama backend.
- `BackendError` — Exception class for all backend failures.
- `get_model_for_tool(config: dict, tool: str) -> str` — Resolves per-tool model override via `{tool}_model` config key, falling back to global `config["model"]`.
- `get_judge_model(config: dict) -> str` — Resolves the quality gate judge model via `get_model_for_tool(config, "judge")`.
- `MAX_TRANSCRIPT_CHARS` — 150,000 character limit for transcript input.
- `DEFAULT_BACKEND` — `"claude-code"`
- `CLI_DEFAULT_MODEL` — `"claude-haiku-4-5"`

## Requires

- `config.GLOBAL_CONFIG_PATH` (from: config) — re-exported for backward compatibility

## Boundary Rules

- `claude-code` backend strips 5 env vars (`CLAUDECODE`, `CLAUDE_CODE_ENTRYPOINT`, `CLAUDE_CODE_DISABLE_FEEDBACK_SURVEY`, `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`, `CLAUDE_CODE_SESSION_ACCESS_TOKEN`) to prevent subprocess hangs.
- `claude-code` subprocess runs from `~/.claude/cyberbrain/` (neutral CWD with no CLAUDE.md).
- `claude-code` always passes `--allowedTools ""` to prevent tool-use in subprocess.
- `claude-code` uses `start_new_session=True` to fully detach from parent process group.
- `claude-code` resolves the `claude` binary with fallback paths for environments without shell PATH (e.g., Claude Desktop MCP process).
- `ollama` backend validates JSON response and performs code-fence stripping as repair.
- All backends raise `BackendError` on failure — callers decide whether to exit, fall back, or propagate.

## Internal Design Notes

- File: `src/cyberbrain/extractors/backends.py`
- `bedrock` imports `anthropic` lazily — not required at module load time
- `ollama` uses `urllib` (stdlib) — no HTTP library dependency
- `claude-code` timeout is configurable via `config["claude_timeout"]` (default 120s)
