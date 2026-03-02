#!/usr/bin/env python3
"""
extract_beats.py
Extracts structured knowledge "beats" from a Claude Code session transcript
and writes them as Obsidian-compatible markdown files.

Usage:
    python3 extract_beats.py \
        --transcript /path/to/transcript.jsonl \
        --session-id abc123 \
        --trigger auto \
        --cwd /Users/dan/code/my-project
"""

import argparse
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path


class BackendError(Exception):
    """Raised when the configured LLM backend cannot produce a response."""


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

GLOBAL_CONFIG_PATH = Path.home() / ".claude" / "knowledge.json"
PROJECT_CONFIG_NAME = "knowledge.local.json"
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

REQUIRED_GLOBAL_FIELDS = ["vault_path", "inbox", "staging_folder"]

DEFAULT_BACKEND = "claude-code"
BEDROCK_DEFAULT_MODEL = "us.anthropic.claude-haiku-4-5-20251001"
CLI_DEFAULT_MODEL = "claude-haiku-4-5"
OLLAMA_DEFAULT_URL = "http://localhost:11434"


def load_global_config() -> dict:
    if not GLOBAL_CONFIG_PATH.exists():
        print(
            f"[extract_beats] Global config not found at {GLOBAL_CONFIG_PATH}. "
            "Create it with vault_path, inbox, and staging_folder.",
            file=sys.stderr,
        )
        sys.exit(0)

    with open(GLOBAL_CONFIG_PATH) as f:
        config = json.load(f)

    missing = [k for k in REQUIRED_GLOBAL_FIELDS if not config.get(k)]
    if missing:
        print(
            f"[extract_beats] Global config missing fields: {missing}. "
            f"Edit {GLOBAL_CONFIG_PATH}.",
            file=sys.stderr,
        )
        sys.exit(0)

    vault_path = Path(config["vault_path"]).expanduser().resolve()

    # Reject placeholder or non-existent paths
    if str(config["vault_path"]) == "/path/to/your/ObsidianVault" or not vault_path.exists():
        print(
            f"[extract_beats] vault_path '{config['vault_path']}' is a placeholder or does not exist. "
            f"Edit {GLOBAL_CONFIG_PATH} with your real vault path.",
            file=sys.stderr,
        )
        sys.exit(0)

    # Reject home directory or filesystem root — indicates misconfiguration
    home = Path.home().resolve()
    root = Path("/").resolve()
    if vault_path == home or vault_path == root:
        print(
            f"[extract_beats] vault_path must not be your home directory or filesystem root. "
            f"Edit {GLOBAL_CONFIG_PATH}.",
            file=sys.stderr,
        )
        sys.exit(0)

    config["vault_path"] = str(vault_path)
    return config


def find_project_config(cwd: str) -> dict:
    """Walk up from cwd looking for .claude/knowledge.local.json."""
    current = Path(cwd).resolve()
    for directory in [current, *current.parents]:
        candidate = directory / ".claude" / PROJECT_CONFIG_NAME
        if candidate.exists():
            with open(candidate) as f:
                return json.load(f)
        # Stop at home directory
        if directory == Path.home():
            break
    return {}


def resolve_config(cwd: str) -> dict:
    global_cfg = load_global_config()
    project_cfg = find_project_config(cwd)
    return {**global_cfg, **project_cfg}


# ---------------------------------------------------------------------------
# Prompt loading
# ---------------------------------------------------------------------------

def load_prompt(filename: str) -> str:
    """Load a prompt file from the prompts directory."""
    path = PROMPTS_DIR / filename
    if not path.exists():
        print(
            f"[extract_beats] Prompt file not found: {path}. "
            "Ensure prompts/ directory is present alongside extractors/.",
            file=sys.stderr,
        )
        sys.exit(0)
    return path.read_text(encoding="utf-8").strip()


# ---------------------------------------------------------------------------
# Transcript parsing
# ---------------------------------------------------------------------------

def parse_jsonl_transcript(transcript_path: str) -> str:
    """
    Parse a JSONL transcript and reconstruct conversation text.
    Extracts user and assistant text turns; skips tool_use, tool_result,
    and thinking blocks.
    Returns a plain-text representation of the conversation.
    """
    turns = []

    with open(transcript_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            entry_type = entry.get("type")
            if entry_type not in ("user", "assistant"):
                continue

            message = entry.get("message", {})
            role = message.get("role", entry_type)
            content = message.get("content", "")

            text = _extract_text_blocks(content)
            if text.strip():
                turns.append(f"[{role.upper()}]\n{text.strip()}")

    return "\n\n---\n\n".join(turns)


def _extract_text_blocks(content) -> str:
    """
    Extract plain text from a content field (string or list of blocks).
    Skips tool_use and thinking blocks — only text blocks are included.
    """
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type", "")
            # Only include plain text blocks; skip tool_use, tool_result, thinking
            if block_type == "text":
                parts.append(block.get("text", ""))
            # tool_use and thinking blocks are intentionally skipped
        return "\n".join(parts)

    return ""


def parse_plain_transcript(text: str) -> str:
    """
    Parse a plain-text transcript, recognising Human:/Assistant: or You:/Claude: prefixes.
    If no role prefixes are detected, returns the text as-is.
    """
    # Check if the text uses role prefixes
    has_prefixes = bool(re.search(r'^(Human|Assistant|You|Claude)\s*:', text, re.MULTILINE))
    if not has_prefixes:
        return text

    # Split on role-prefixed lines, preserving the structure
    turns = []
    current_role = None
    current_lines = []

    for line in text.splitlines():
        m = re.match(r'^(Human|Assistant|You|Claude)\s*:\s*(.*)', line)
        if m:
            if current_role is not None and current_lines:
                role_label = "USER" if current_role in ("Human", "You") else "ASSISTANT"
                turns.append(f"[{role_label}]\n" + "\n".join(current_lines).strip())
            current_role = m.group(1)
            current_lines = [m.group(2)]
        else:
            if current_role is not None:
                current_lines.append(line)

    if current_role is not None and current_lines:
        role_label = "USER" if current_role in ("Human", "You") else "ASSISTANT"
        turns.append(f"[{role_label}]\n" + "\n".join(current_lines).strip())

    return "\n\n---\n\n".join(turns)


# ---------------------------------------------------------------------------
# LLM backends
# ---------------------------------------------------------------------------

# Rough token budget: haiku has 200k context. We'll send up to ~150k chars of transcript.
MAX_TRANSCRIPT_CHARS = 150_000

# Env vars that cause nested-session hangs when claude -p is spawned as a subprocess
_STRIP_VARS = {
    "CLAUDECODE",
    "CLAUDE_CODE_ENTRYPOINT",
    "CLAUDE_CODE_DISABLE_FEEDBACK_SURVEY",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",
}


def _call_claude_code(system_prompt: str, user_message: str, config: dict) -> str:
    """Call claude CLI subprocess (claude-code backend)."""
    import shutil
    import subprocess

    claude_path = config.get("claude_path", "claude")
    if not shutil.which(claude_path):
        raise BackendError(
            f"'claude' CLI not found at {claude_path!r} (backend=claude-code). "
            "Ensure Claude Code is installed and 'claude' is in PATH, "
            "or set claude_path in knowledge.json, "
            "or switch to backend=bedrock or backend=ollama in knowledge.json."
        )

    model = config.get("model", CLI_DEFAULT_MODEL)
    full_prompt = f"{system_prompt}\n\n---\n\n{user_message}"

    # Always pass --allowedTools "" for extraction — enforced in code, not config (M1 security).
    # This prevents the subprocess from sending PermissionRequest IPC events to the parent TUI.
    cmd = [claude_path, "-p", "--allowedTools", "", "--model", model,
           "--no-session-persistence", "--max-turns", "1"]
    print(f"[extract_beats] Using claude-code backend (model={model})", file=sys.stderr)

    # Strip Claude Code session vars so claude -p can run as a clean subprocess.
    env = {k: v for k, v in os.environ.items() if k not in _STRIP_VARS}

    subprocess_cwd = config.get("subprocess_cwd") or None

    try:
        result = subprocess.run(
            cmd,
            input=full_prompt,
            capture_output=True,
            text=True,
            timeout=config.get("claude_timeout", 120),
            env=env,
            cwd=subprocess_cwd,
        )
    except subprocess.TimeoutExpired:
        raise BackendError(
            f"claude -p timed out after {config.get('claude_timeout', 120)}s. "
            "Increase claude_timeout in knowledge.json or switch to a faster backend."
        )
    except Exception as e:
        raise BackendError(f"claude -p failed to start: {e}")

    if result.returncode != 0:
        stderr_snippet = result.stderr[:500].strip() or "(empty)"
        raise BackendError(
            f"claude -p exited with code {result.returncode}. "
            f"Stderr: {stderr_snippet}"
        )

    output = result.stdout.strip()
    if not output:
        stderr_snippet = result.stderr[:300].strip() or "(empty)"
        raise BackendError(
            "claude -p exited successfully (code 0) but produced no output. "
            f"Stderr: {stderr_snippet}. "
            "This may indicate an auth issue, rate limiting, or an incompatible "
            "claude CLI version. Try: claude -p --model claude-haiku-4-5 "
            "--no-session-persistence --max-turns 1 'respond with: ok'"
        )
    return output


def _call_bedrock(system_prompt: str, user_message: str, config: dict) -> str:
    """Call Anthropic Bedrock via the anthropic SDK."""
    try:
        import anthropic
    except ImportError:
        raise BackendError(
            "'anthropic' package not installed. "
            "Run: pip install anthropic[bedrock]  (in the MCP venv: ~/.claude/mcp-venv/bin/pip install anthropic[bedrock])"
        )

    region = config.get("bedrock_region", "us-east-1")
    model = config.get("model", BEDROCK_DEFAULT_MODEL)
    print(f"[extract_beats] Using Bedrock backend (region={region}, model={model})", file=sys.stderr)

    try:
        client = anthropic.AnthropicBedrock(aws_region=region)
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
    except Exception as e:
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
    import urllib.request
    import urllib.error

    ollama_url = config.get("ollama_url", OLLAMA_DEFAULT_URL).rstrip("/")
    model = config.get("model", "llama3.2")
    timeout = config.get("claude_timeout", 120)

    print(f"[extract_beats] Using Ollama backend (url={ollama_url}, model={model})", file=sys.stderr)

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
    except Exception as e:
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
        # Valid JSON — return it as-is
        return content
    except json.JSONDecodeError:
        # Attempt to strip markdown code fences
        stripped = re.sub(r"^```(?:json)?\s*", "", content)
        stripped = re.sub(r"\s*```$", "", stripped).strip()
        try:
            json.loads(stripped)
            return stripped
        except json.JSONDecodeError:
            raise BackendError(
                "Ollama returned content that is not valid JSON even after stripping code fences."
            )


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


# ---------------------------------------------------------------------------
# Vault CLAUDE.md reading
# ---------------------------------------------------------------------------

def read_vault_claude_md(vault_path: str) -> str | None:
    """Read the vault's CLAUDE.md file if it exists. Returns full text or None."""
    claude_md_path = Path(vault_path) / "CLAUDE.md"
    if claude_md_path.exists():
        try:
            return claude_md_path.read_text(encoding="utf-8")
        except OSError:
            return None
    return None


# ---------------------------------------------------------------------------
# Beat extraction via LLM
# ---------------------------------------------------------------------------

def extract_beats(transcript_text: str, config: dict, trigger: str, cwd: str) -> list[dict]:
    project_name = config.get("project_name", Path(cwd).name)

    # Truncate transcript if too long (keep tail — most recent content is most valuable)
    if len(transcript_text) > MAX_TRANSCRIPT_CHARS:
        transcript_text = "...[earlier content truncated]...\n\n" + transcript_text[-MAX_TRANSCRIPT_CHARS:]

    # Read vault CLAUDE.md for type vocabulary context
    vault_claude_md = read_vault_claude_md(config["vault_path"])

    if vault_claude_md:
        vault_claude_md_section = (
            "<vault_claude_md>\n"
            "The following is the vault's CLAUDE.md, which defines the type vocabulary "
            "and filing conventions for this vault. Use the type vocabulary defined here "
            "instead of the default four-type vocabulary.\n\n"
            f"{vault_claude_md}\n"
            "</vault_claude_md>\n\n"
        )
    else:
        vault_claude_md_section = (
            "No vault CLAUDE.md was found. Use the default four-type vocabulary only: "
            "decision, insight, problem, reference.\n\n"
        )

    system_prompt = load_prompt("extract-beats-system.md")
    user_message = load_prompt("extract-beats-user.md").format_map({
        "project_name": project_name,
        "cwd": cwd,
        "trigger": trigger,
        "transcript": transcript_text,
        "vault_claude_md_section": vault_claude_md_section,
    })

    raw = call_model(system_prompt, user_message, config)
    if not raw:
        return []

    # Strip markdown code fences if model added them despite instructions
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        # Use raw_decode so trailing explanatory text after the JSON is ignored
        beats, _ = json.JSONDecoder().raw_decode(raw.lstrip())
    except json.JSONDecodeError as e:
        print(f"[extract_beats] Failed to parse model response as JSON: {e}", file=sys.stderr)
        print(f"[extract_beats] Raw response: {raw[:500]}", file=sys.stderr)
        return []

    if not isinstance(beats, list):
        print(f"[extract_beats] Model returned non-list JSON: {type(beats)}", file=sys.stderr)
        return []

    return beats


# ---------------------------------------------------------------------------
# Beat writing
# ---------------------------------------------------------------------------

VALID_TYPES = {"decision", "insight", "problem", "reference"}
VALID_SCOPES = {"project", "general"}

_FILENAME_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def make_filename(title: str) -> str:
    """Convert a title to a clean human-readable filename."""
    clean = _FILENAME_INVALID.sub('', title)
    clean = re.sub(r'\s+', ' ', clean).strip()
    if len(clean) > 80:
        clean = clean[:80].rsplit(' ', 1)[0].strip()
    return clean + '.md'


def resolve_output_dir(beat: dict, config: dict) -> Path:
    """
    Route a beat to the correct vault folder based on scope and project config.
    Returns the absolute directory path (created if needed).
    """
    vault = Path(config["vault_path"])
    if beat.get("scope") == "project" and config.get("vault_folder"):
        folder = config["vault_folder"]
    elif config.get("inbox"):
        folder = config["inbox"]
    else:
        folder = config.get("staging_folder", "AI/Claude-Inbox")
    output_dir = vault / folder
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def write_beat(beat: dict, config: dict, session_id: str, cwd: str, now: datetime) -> Path:
    """Write a single beat to a markdown file. Returns the file path."""
    beat_type = beat.get("type", "reference")
    if beat_type not in VALID_TYPES:
        beat_type = "reference"

    scope = beat.get("scope", "general")
    if scope not in VALID_SCOPES:
        scope = "general"

    title = beat.get("title", "Untitled").strip()
    summary = beat.get("summary", "").strip()
    tags = beat.get("tags", [])
    body = beat.get("body", "").strip()

    if not isinstance(tags, list):
        tags = []
    tags = [str(t).lower() for t in tags if t]

    project_name = config.get("project_name", Path(cwd).name)
    date_str = now.strftime("%Y-%m-%dT%H:%M:%S")

    beat_id = str(uuid.uuid4())

    output_dir = resolve_output_dir(beat, config)

    # Handle filename collisions — prepend number so canonical name is unmodified
    output_path = output_dir / make_filename(title)
    counter = 2
    while output_path.exists():
        output_path = output_dir / f"{counter} {make_filename(title)}"
        counter += 1

    # Use json.dumps for string fields to safely handle quotes and special chars.
    # JSON string syntax is valid YAML scalar syntax.
    front_matter = f"""---
id: {beat_id}
date: {date_str}
session_id: {session_id}
type: {beat_type}
scope: {scope}
title: {json.dumps(title)}
project: {project_name}
cwd: {cwd}
tags: {json.dumps(tags)}
related: []
status: completed
summary: {json.dumps(summary)}
---"""

    content = f"{front_matter}\n\n## {title}\n\n{body}\n"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    return output_path


# ---------------------------------------------------------------------------
# Vault search
# ---------------------------------------------------------------------------

def search_vault(beat: dict, vault_path: str, max_results: int = 5) -> list[str]:
    """
    Search vault for files related to a beat by tags and title keywords.
    Returns up to max_results paths, ranked by keyword match count (most first),
    using file mtime as tiebreaker.
    """
    import subprocess

    terms = list(beat.get("tags", []))
    terms += [w for w in beat["title"].split() if len(w) >= 4][:5]
    terms = list(dict.fromkeys(terms))  # deduplicate, preserve order

    # Track match count and mtime for each found path
    found_counts: dict[str, int] = {}   # path → match count
    found_mtime: dict[str, float] = {}  # path → mtime

    for term in terms:
        result = subprocess.run(
            ["grep", "-r", "-l", "--include=*.md", "-i", term, vault_path],
            capture_output=True, text=True
        )
        for path in result.stdout.strip().splitlines():
            if path:
                found_counts[path] = found_counts.get(path, 0) + 1
                if path not in found_mtime:
                    try:
                        found_mtime[path] = os.path.getmtime(path)
                    except OSError:
                        found_mtime[path] = 0.0

    # Rank by match count (descending), then mtime (descending) as tiebreaker
    ranked = sorted(
        found_counts.keys(),
        key=lambda p: (found_counts[p], found_mtime.get(p, 0.0)),
        reverse=True,
    )
    return ranked[:max_results]


# ---------------------------------------------------------------------------
# Autofile
# ---------------------------------------------------------------------------

def _is_within_vault(vault: Path, target: Path) -> bool:
    """Return True if target resolves to a path within vault."""
    try:
        target.resolve().relative_to(vault.resolve())
        return True
    except ValueError:
        return False


def autofile_beat(beat: dict, config: dict, session_id: str, cwd: str, now: datetime,
                   vault_context: str | None = None) -> Path | None:
    """File a beat intelligently into the vault using LLM judgment."""
    vault_path = config["vault_path"]

    # Load vault filing context from CLAUDE.md if not pre-cached by caller
    if vault_context is None:
        vault_context_text = read_vault_claude_md(vault_path)
        vault_context = vault_context_text if vault_context_text is not None else \
            "File notes using human-readable names with spaces. Use types: decision, insight, problem, reference."

    # Search for related vault docs — ranked by keyword match count, up to 5 candidates
    related_paths = search_vault(beat, vault_path, max_results=5)
    related_docs = []
    for path in related_paths:
        try:
            content = Path(path).read_text(encoding="utf-8")
            rel = os.path.relpath(path, vault_path)
            related_docs.append(f"### {rel}\n\n{content[:2000]}")
        except OSError:
            pass

    # Get top-level folder listing
    try:
        vault_folders = "\n".join(
            str(p.relative_to(vault_path))
            for p in sorted(Path(vault_path).iterdir())
            if p.is_dir() and not p.name.startswith(".")
        )
    except OSError:
        vault_folders = ""

    system_prompt = load_prompt("autofile-system.md")
    user_message = load_prompt("autofile-user.md").format_map({
        "beat_json": json.dumps(beat, indent=2),
        "related_docs": "\n\n---\n\n".join(related_docs) if related_docs else "(none found)",
        "vault_context": vault_context,
        "vault_folders": vault_folders or "(empty)",
    })

    # Always use the same model as extraction — no separate autofile model
    print(f"[extract_beats] autofile: using model for filing decision", file=sys.stderr)

    try:
        raw = call_model(system_prompt, user_message, config)
    except BackendError as e:
        print(f"[extract_beats] autofile: backend error, falling back to inbox: {e}", file=sys.stderr)
        return write_beat(beat, config, session_id, cwd, now)
    if not raw:
        # Fall back to inbox write
        return write_beat(beat, config, session_id, cwd, now)

    # Strip code fences
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        decision = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"[extract_beats] autofile: bad JSON from model: {e}", file=sys.stderr)
        return write_beat(beat, config, session_id, cwd, now)

    action = decision.get("action")
    vault = Path(vault_path)

    if action == "extend":
        target_rel = decision.get("target_path", "")
        target = vault / target_rel
        if not _is_within_vault(vault, target):
            print(f"[extract_beats] autofile: path traversal rejected: {target_rel}", file=sys.stderr)
            return write_beat(beat, config, session_id, cwd, now)
        insertion = decision.get("insertion", "")
        if not target.exists() or not insertion:
            return write_beat(beat, config, session_id, cwd, now)
        with open(target, "a", encoding="utf-8") as f:
            f.write(f"\n\n{insertion.strip()}\n")
        print(f"[extract_beats] autofile: extended {target}", file=sys.stderr)
        return target

    elif action == "create":
        rel_path = decision.get("path", "")
        content = decision.get("content", "")
        if not rel_path or not content:
            return write_beat(beat, config, session_id, cwd, now)
        output_path = vault / rel_path
        if not _is_within_vault(vault, output_path):
            print(f"[extract_beats] autofile: path traversal rejected: {rel_path}", file=sys.stderr)
            return write_beat(beat, config, session_id, cwd, now)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Collision handling: check if target already exists
        if output_path.exists():
            # Read existing note's tags frontmatter field
            existing_tags = _read_frontmatter_tags(output_path)
            beat_tags = set(str(t).lower() for t in beat.get("tags", []) if t)
            overlap = len(existing_tags & beat_tags)

            if overlap >= 2:
                # Related enough — treat as extend instead
                with open(output_path, "a", encoding="utf-8") as f:
                    f.write(f"\n\n{content.strip()}\n")
                print(f"[extract_beats] autofile: collision resolved as extend (tag overlap={overlap}): {output_path}", file=sys.stderr)
                return output_path
            else:
                # Unrelated — generate more specific title using most distinguishing tag
                beat_tags_list = [str(t).lower() for t in beat.get("tags", []) if t]
                distinguishing_tag = beat_tags_list[0] if beat_tags_list else "new"
                base_stem = output_path.stem
                specific_path = output_path.parent / f"{base_stem} — {distinguishing_tag}.md"

                if specific_path.exists():
                    # Last resort: incrementing counter
                    counter = 2
                    specific_path = output_path.parent / f"{counter} {output_path.name}"
                    while specific_path.exists():
                        counter += 1
                        specific_path = output_path.parent / f"{counter} {output_path.name}"

                output_path = specific_path

        output_path.write_text(content, encoding="utf-8")
        print(f"[extract_beats] autofile: created {output_path}", file=sys.stderr)
        return output_path

    else:
        print(f"[extract_beats] autofile: unknown action '{action}', falling back", file=sys.stderr)
        return write_beat(beat, config, session_id, cwd, now)


def _read_frontmatter_tags(path: Path) -> set:
    """Read the tags field from YAML frontmatter of a markdown file. Returns a set of lowercase strings."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return set()

    # Extract frontmatter block
    m = re.match(r'^---\s*\n(.*?)\n---', text, re.DOTALL)
    if not m:
        return set()

    frontmatter = m.group(1)

    # Look for tags: field — supports both list form and inline JSON
    tags_match = re.search(r'^tags:\s*(.+)$', frontmatter, re.MULTILINE)
    if not tags_match:
        return set()

    tags_raw = tags_match.group(1).strip()

    # Try JSON array first (our format)
    try:
        tags_list = json.loads(tags_raw)
        if isinstance(tags_list, list):
            return {str(t).lower() for t in tags_list if t}
    except (json.JSONDecodeError, ValueError):
        pass

    # Try YAML-style list: ["tag1", "tag2"] or [tag1, tag2]
    # Fall back to splitting on commas inside brackets
    m2 = re.match(r'^\[(.*)\]$', tags_raw)
    if m2:
        inner = m2.group(1)
        parts = [p.strip().strip('"\'') for p in inner.split(',')]
        return {p.lower() for p in parts if p}

    return set()


# ---------------------------------------------------------------------------
# Deduplication log
# ---------------------------------------------------------------------------

EXTRACT_LOG_PATH = Path.home() / ".claude" / "logs" / "kg-extract.log"


def is_session_already_extracted(session_id: str) -> bool:
    """Check if a session ID already appears in the deduplication log."""
    if not EXTRACT_LOG_PATH.exists():
        return False
    try:
        text = EXTRACT_LOG_PATH.read_text(encoding="utf-8")
        for line in text.splitlines():
            parts = line.split("\t")
            if len(parts) >= 2 and parts[1] == session_id:
                return True
        return False
    except OSError as e:
        print(f"[extract_beats] Warning: could not read deduplication log: {e}", file=sys.stderr)
        return False


def write_extract_log_entry(session_id: str, beat_count: int) -> None:
    """Append a tab-separated entry to the deduplication log."""
    try:
        EXTRACT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        entry = f"{timestamp}\t{session_id}\t{beat_count}\n"
        with open(EXTRACT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(entry)
    except OSError as e:
        print(f"[extract_beats] Warning: could not write deduplication log: {e}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Daily journal
# ---------------------------------------------------------------------------

def write_journal_entry(written_paths: list[Path], config: dict, session_id: str,
                         project_name: str, now: datetime) -> None:
    journal_folder = config.get("journal_folder", "AI/Journal")
    journal_name_tpl = config.get("journal_name", "%Y-%m-%d")
    date_str = now.strftime(journal_name_tpl)

    vault = Path(config["vault_path"])
    journal_dir = vault / journal_folder
    journal_dir.mkdir(parents=True, exist_ok=True)
    journal_path = journal_dir / f"{date_str}.md"

    # Build wikilinks for each written file (shortest-path format — title only)
    links = []
    for path in written_paths:
        stem = path.stem
        links.append(f"- [[{stem}]]")
    links_block = "\n".join(links) if links else "- (none)"

    # Format: ## Session abc12345 — YYYY-MM-DD HH:MM UTC (project-name)
    timestamp_str = now.strftime("%Y-%m-%d %H:%M")
    session_block = (
        f"\n## Session {session_id[:8]} — {timestamp_str} UTC ({project_name})\n\n"
        f"{len(written_paths)} note(s) captured:\n{links_block}\n"
    )

    if journal_path.exists():
        # Append to existing daily file
        with open(journal_path, "a", encoding="utf-8") as f:
            f.write(session_block)
    else:
        # Create new daily file
        header = f"---\ntype: journal\ndate: {now.strftime('%Y-%m-%d')}\n---\n\n# {date_str}\n"
        journal_path.write_text(header + session_block, encoding="utf-8")

    print(f"[extract_beats] Journal updated: {journal_path}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Extract knowledge beats from a Claude Code transcript")
    parser.add_argument("--transcript", help="Path to transcript JSONL file")
    parser.add_argument("--beats-json", help="Path to pre-extracted beats JSON (skips transcript parsing and API call)")
    parser.add_argument("--session-id", required=True, help="Session ID")
    parser.add_argument("--trigger", default="auto", help="Compaction trigger type (auto, manual, session-end, or any value Claude passes)")
    parser.add_argument("--cwd", required=True, help="Working directory of the Claude Code session")
    parser.add_argument("--dry-run", action="store_true", help="Preview beats without writing to vault or log")
    args = parser.parse_args()

    if not args.transcript and not args.beats_json:
        print("[extract_beats] Provide --transcript or --beats-json.", file=sys.stderr)
        sys.exit(1)

    config = resolve_config(args.cwd)
    autofile_enabled = config.get("autofile", False)
    journal_enabled = config.get("daily_journal", False)

    # Derive session ID from transcript filename stem if possible
    session_id = args.session_id
    if args.transcript:
        transcript_stem = Path(args.transcript).stem
        if transcript_stem:
            session_id = transcript_stem

    # Deduplication check
    if is_session_already_extracted(session_id):
        print(f"[extract_beats] Session '{session_id}' already extracted. Skipping.", file=sys.stderr)
        sys.exit(0)

    if args.beats_json:
        print(f"[extract_beats] Loading pre-extracted beats from: {args.beats_json}", file=sys.stderr)
        try:
            with open(args.beats_json, "r", encoding="utf-8") as f:
                beats = json.load(f)
        except Exception as e:
            print(f"[extract_beats] Failed to load beats JSON: {e}", file=sys.stderr)
            sys.exit(1)
        if not isinstance(beats, list):
            print("[extract_beats] --beats-json must contain a JSON array.", file=sys.stderr)
            sys.exit(1)
    else:
        print(f"[extract_beats] Parsing transcript: {args.transcript}", file=sys.stderr)
        transcript_text = parse_jsonl_transcript(args.transcript)

        if not transcript_text.strip():
            print("[extract_beats] Transcript is empty or has no user/assistant turns. Nothing to extract.", file=sys.stderr)
            sys.exit(0)

        print("[extract_beats] Calling LLM to extract beats...", file=sys.stderr)
        try:
            beats = extract_beats(transcript_text, config, args.trigger, args.cwd)
        except BackendError as e:
            print(f"[extract_beats] Backend error: {e}", file=sys.stderr)
            sys.exit(0)

    if not beats:
        print("[extract_beats] No beats extracted.", file=sys.stderr)
        sys.exit(0)

    if args.dry_run:
        print(f"[extract_beats] [DRY RUN] Would write {len(beats)} beat(s):", file=sys.stderr)
        for beat in beats:
            print(f"  - {beat.get('title', '?')} ({beat.get('type', '?')})", file=sys.stderr)
        sys.exit(0)

    now = datetime.now(timezone.utc)
    written = []

    # Cache vault CLAUDE.md once for the whole autofile run (avoids N disk reads for N beats)
    vault_context = None
    if autofile_enabled:
        vault_context_text = read_vault_claude_md(config["vault_path"])
        vault_context = vault_context_text if vault_context_text is not None else \
            "File notes using human-readable names with spaces. Use types: decision, insight, problem, reference."

    for beat in beats:
        try:
            if autofile_enabled:
                path = autofile_beat(beat, config, session_id, args.cwd, now, vault_context=vault_context)
            else:
                path = write_beat(beat, config, session_id, args.cwd, now)
            if path:
                written.append(path)
                print(f"[extract_beats] Wrote: {path}", file=sys.stderr)
        except Exception as e:
            print(f"[extract_beats] Failed on '{beat.get('title', '?')}': {e}", file=sys.stderr)

    if journal_enabled and written:
        project_name = config.get("project_name", Path(args.cwd).name)
        write_journal_entry(written, config, session_id, project_name, now)

    # Write deduplication log entry
    write_extract_log_entry(session_id, len(written))

    print(f"[extract_beats] Done. {len(written)} beat(s) written.", file=sys.stderr)


if __name__ == "__main__":
    main()
