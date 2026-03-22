"""
backends.py

LLM backend implementations for cyberbrain: claude-code, bedrock, ollama.
"""

import json
import os
import re
import sys
from pathlib import Path

from cyberbrain.extractors.config import (
    GLOBAL_CONFIG_PATH,  # noqa: F401 — re-exported for callers
)


class BackendError(Exception):
    """Raised when the configured LLM backend cannot produce a response."""


# Rough token budget: haiku has 200k context. We'll send up to ~150k chars of transcript.
MAX_TRANSCRIPT_CHARS = 150_000

# Env vars that cause nested-session hangs when claude -p is spawned as a subprocess
_STRIP_VARS = {
    "CLAUDECODE",
    "CLAUDE_CODE_ENTRYPOINT",
    "CLAUDE_CODE_DISABLE_FEEDBACK_SURVEY",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",
    "CLAUDE_CODE_SESSION_ACCESS_TOKEN",
}

DEFAULT_BACKEND = "claude-code"
BEDROCK_DEFAULT_MODEL = "us.anthropic.claude-haiku-4-5-20251001"
CLI_DEFAULT_MODEL = "claude-haiku-4-5"
OLLAMA_DEFAULT_URL = "http://localhost:11434"


def _call_claude_code(system_prompt: str, user_message: str, config: dict) -> str:
    """Call claude CLI subprocess (claude-code backend)."""
    import shutil
    import subprocess

    claude_path = config.get("claude_path", "claude")

    # Resolve the binary. If not found on PATH (common in Claude Desktop's isolated
    # environment), try well-known install locations before giving up.
    resolved = shutil.which(claude_path)
    if not resolved and claude_path == "claude":
        _FALLBACK_PATHS = [
            "/opt/homebrew/bin/claude",  # macOS Apple Silicon (Homebrew)
            "/usr/local/bin/claude",  # macOS Intel / Linux (Homebrew)
            os.path.expanduser("~/.local/bin/claude"),
            "/usr/bin/claude",
        ]
        for candidate in _FALLBACK_PATHS:
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                resolved = candidate
                break

    if not resolved:
        raise BackendError(
            "'claude' CLI not found (backend=claude-code). "
            "Claude Desktop runs MCP servers without your shell PATH. "
            "Fix: add 'claude_path' to ~/.claude/cyberbrain/config.json with the full path, e.g.: "
            '{"claude_path": "/opt/homebrew/bin/claude"}  '
            "Or find the path with: which claude"
        )

    claude_path = resolved

    model = config.get("model", CLI_DEFAULT_MODEL)
    full_prompt = f"{system_prompt}\n\n---\n\n{user_message}"

    # Always pass --allowedTools "" for extraction — enforced in code, not config (M1 security).
    # This prevents the subprocess from sending PermissionRequest IPC events to the parent TUI.
    # --max-turns 3: haiku occasionally needs >1 internal turn on large transcripts; 3 is
    # enough headroom without opening up tool-use loops (allowedTools "" blocks all tools).
    cmd = [
        claude_path,
        "-p",
        "--allowedTools",
        "",
        "--model",
        model,
        "--no-session-persistence",
        "--max-turns",
        "3",
    ]
    print(f"[extract_beats] Using claude-code backend (model={model})", file=sys.stderr)

    # Strip Claude Code session vars so claude -p can run as a clean subprocess.
    env = {k: v for k, v in os.environ.items() if k not in _STRIP_VARS}

    # Use a neutral cwd with no CLAUDE.md to prevent project config injection.
    # Falls back to home directory if the cyberbrain dir doesn't exist yet.
    default_cwd = str(
        Path.home() / ".claude" / "cyberbrain"
    )  # dynamic: tests monkeypatch Path.home()
    subprocess_cwd = config.get("subprocess_cwd") or default_cwd

    try:
        result = subprocess.run(
            cmd,
            input=full_prompt,
            capture_output=True,
            text=True,
            timeout=config.get("claude_timeout", 120),
            env=env,
            cwd=subprocess_cwd,
            start_new_session=True,
        )
    except subprocess.TimeoutExpired:
        raise BackendError(
            f"claude -p timed out after {config.get('claude_timeout', 120)}s. "
            "Increase claude_timeout in cyberbrain.json or switch to a faster backend."
        )
    except Exception as e:  # intentional: subprocess.run can raise OSError, FileNotFoundError, PermissionError, etc.
        raise BackendError(f"claude -p failed to start: {e}")

    if result.returncode != 0:
        stderr_snippet = result.stderr[:500].strip() or "(empty)"
        raise BackendError(
            f"claude -p exited with code {result.returncode}. Stderr: {stderr_snippet}"
        )

    output = result.stdout.strip()
    if not output:
        stderr_snippet = result.stderr[:300].strip() or "(empty)"
        raise BackendError(
            "claude -p exited successfully (code 0) but produced no output. "
            f"Stderr: {stderr_snippet}. "
            "This may indicate an auth issue, rate limiting, or an incompatible "
            "claude CLI version. Try: claude -p --model claude-haiku-4-5 "
            "--no-session-persistence --max-turns 3 'respond with: ok'"
        )
    # Detect CLI-level error messages written to stdout (e.g. "Error: Reached max turns (3)")
    if output.startswith("Error:"):
        raise BackendError(
            f"claude -p returned a CLI error: {output}. "
            "If 'Reached max turns', the transcript may be too long — try raising "
            "claude_timeout in cyberbrain.json, or reduce the transcript with --since."
        )
    return output


def _call_bedrock(system_prompt: str, user_message: str, config: dict) -> str:
    """Call Anthropic Bedrock via the anthropic SDK."""
    try:
        import anthropic  # type: ignore[import-not-found]  # optional dependency
    except ImportError:
        raise BackendError(
            "'anthropic' package not installed. "
            "Run: pip install anthropic[bedrock]  (in the MCP venv: ~/.claude/cyberbrain/venv/bin/pip install anthropic[bedrock])"
        )

    region = config.get("bedrock_region", "us-east-1")
    model = config.get("model", BEDROCK_DEFAULT_MODEL)
    print(
        f"[extract_beats] Using Bedrock backend (region={region}, model={model})",
        file=sys.stderr,
    )

    try:
        client = anthropic.AnthropicBedrock(aws_region=region)
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
    except Exception as e:  # intentional: Bedrock SDK raises many exception types (auth, rate limit, network, etc.)
        raise BackendError(f"Bedrock API call failed ({type(e).__name__}): {e}")

    if not response.content:
        raise BackendError("Bedrock API returned an empty content array.")

    block = response.content[0]
    if not hasattr(block, "text"):
        raise BackendError(
            f"Bedrock API returned an unexpected content block type: {type(block).__name__}. "
            "Expected a text block."
        )

    output = block.text.strip()
    if not output:
        raise BackendError("Bedrock API returned an empty response text.")
    return output


def _call_ollama(system_prompt: str, user_message: str, config: dict) -> str:
    """Call a local Ollama instance via its /api/chat endpoint using urllib."""
    import urllib.error
    import urllib.request

    ollama_url = config.get("ollama_url", OLLAMA_DEFAULT_URL).rstrip("/")
    model = config.get("model", "llama3.2")
    timeout = config.get("claude_timeout", 120)

    print(
        f"[extract_beats] Using Ollama backend (url={ollama_url}, model={model})",
        file=sys.stderr,
    )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_predict": 4096,
        },
        "format": "json",
    }

    request_body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{ollama_url}/api/chat",
        data=request_body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            response_body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise BackendError(f"Ollama HTTP error {e.code}: {e.reason}")
    except urllib.error.URLError as e:
        raise BackendError(f"Ollama connection error: {e.reason}")
    except TimeoutError:
        raise BackendError(f"Ollama request timed out after {timeout}s.")
    except Exception as e:  # intentional: catches any remaining urllib errors (e.g. ssl.SSLError, socket.gaierror)
        raise BackendError(f"Ollama request failed: {e}")

    try:
        data = json.loads(response_body)
    except json.JSONDecodeError as e:
        raise BackendError(f"Ollama returned invalid JSON response: {e}")

    try:
        content = data["message"]["content"]
    except (KeyError, TypeError) as e:
        raise BackendError(f"Ollama response missing message.content field: {e}")

    # JSON repair: strip markdown code fences if present, retry parse once
    content = content.strip()
    try:
        json.loads(content)
        return content
    except json.JSONDecodeError:
        stripped = re.sub(r"^```(?:json)?\s*", "", content)
        stripped = re.sub(r"\s*```$", "", stripped).strip()
        try:
            json.loads(stripped)
            return stripped
        except json.JSONDecodeError:
            raise BackendError(
                "Ollama returned content that is not valid JSON even after stripping code fences."
            )


def get_model_for_tool(config: dict, tool: str) -> str:
    """Return the model to use for a specific tool.

    Checks for a dedicated <tool>_model config key (e.g. restructure_model,
    enrich_model, judge_model); falls back to the global model if not set.
    """
    tool_key = f"{tool}_model"
    return config.get(tool_key, config.get("model", CLI_DEFAULT_MODEL))


def get_judge_model(config: dict) -> str:
    """Return the model to use for quality gate judgments.

    Checks for a dedicated judge_model config key; falls back to the
    default model if not set. Delegates to get_model_for_tool internally.
    """
    return get_model_for_tool(config, "judge")


def call_model(system_prompt: str, user_message: str, config: dict) -> str:
    backend = config.get("backend", DEFAULT_BACKEND)
    if backend == "claude-code":
        return _call_claude_code(system_prompt, user_message, config)
    elif backend == "bedrock":
        return _call_bedrock(system_prompt, user_message, config)
    elif backend == "ollama":
        return _call_ollama(system_prompt, user_message, config)
    else:
        raise BackendError(
            f"Unknown backend '{backend}'. Valid options: claude-code, bedrock, ollama."
        )
