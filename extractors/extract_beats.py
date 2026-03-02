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

    vault_path = Path(config["vault_path"]).expanduser()
    if str(vault_path) == "/path/to/your/ObsidianVault" or not vault_path.exists():
        print(
            f"[extract_beats] vault_path '{config['vault_path']}' is a placeholder or does not exist. "
            f"Edit {GLOBAL_CONFIG_PATH} with your real vault path.",
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

def parse_transcript(transcript_path: str) -> str:
    """
    Parse the JSONL transcript and reconstruct conversation text.
    Returns a plain-text representation of user + assistant turns.
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

            text = extract_text(content)
            if text.strip():
                turns.append(f"[{role.upper()}]\n{text.strip()}")

    return "\n\n---\n\n".join(turns)


def extract_text(content) -> str:
    """Extract plain text from a content field (string or list of blocks)."""
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type", "")
            if block_type == "text":
                parts.append(block.get("text", ""))
            elif block_type == "tool_result":
                # Include tool results as context, but trim if huge
                inner = block.get("content", "")
                if isinstance(inner, list):
                    inner = " ".join(
                        b.get("text", "") for b in inner
                        if isinstance(b, dict) and b.get("type") == "text"
                    )
                if isinstance(inner, str) and inner.strip():
                    parts.append(f"[tool result: {inner[:500]}{'...' if len(inner) > 500 else ''}]")
            # Skip thinking and tool_use blocks — too noisy for extraction
        return "\n".join(parts)

    return ""


# ---------------------------------------------------------------------------
# Beat extraction via LLM backend
# ---------------------------------------------------------------------------

# Rough token budget: haiku has 200k context. We'll send up to ~150k chars of transcript.
MAX_TRANSCRIPT_CHARS = 150_000

DEFAULT_BACKEND = "claude-cli"

BEDROCK_DEFAULT_MODEL = "us.anthropic.claude-haiku-4-5-20251001"
DIRECT_DEFAULT_MODEL  = "claude-haiku-4-5"

CLI_DEFAULT_MODEL = "claude-haiku-4-5"


def _call_claude_cli(system_prompt: str, user_message: str, config: dict) -> str:
    import shutil
    import subprocess

    claude_path = config.get("claude_path", "claude")
    if not shutil.which(claude_path):
        raise BackendError(
            f"'claude' CLI not found at {claude_path!r} (backend=claude-cli). "
            "Ensure Claude Code is installed and 'claude' is in PATH, "
            "or set claude_path in knowledge.json, "
            "or switch to backend=anthropic or backend=bedrock in knowledge.json."
        )

    model = config.get("claude_model", CLI_DEFAULT_MODEL)
    full_prompt = f"{system_prompt}\n\n---\n\n{user_message}"

    # Allow the caller to grant specific tools via config; default to none.
    # The extraction prompt is pure text→JSON and needs no tools. Keeping the
    # tool list empty prevents the subprocess from sending PermissionRequest IPC
    # events to the parent session's TUI, which would cause it to hang
    # indefinitely waiting for a human to click approve.
    allowed_tools = config.get("claude_allowed_tools", "")
    cmd = [claude_path, "-p", "--tools", allowed_tools, "--model", model, "--no-session-persistence", "--max-turns", "1"]
    print(f"[extract_beats] Using claude-cli backend (model={model})", file=sys.stderr)

    # Strip Claude Code session vars so claude -p can run as a clean subprocess.
    # CLAUDECODE triggers the nested-session guard. CLAUDE_CODE_ENTRYPOINT and the
    # DISABLE_* vars prevent the child process from establishing API connections
    # (confirmed: github.com/anthropics/claude-code/issues/26190).
    _STRIP_VARS = {
        "CLAUDECODE",
        "CLAUDE_CODE_ENTRYPOINT",
        "CLAUDE_CODE_DISABLE_FEEDBACK_SURVEY",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",
    }
    env = {k: v for k, v in os.environ.items() if k not in _STRIP_VARS}

    # Allow callers to isolate the subprocess from any parent project's CLAUDE.md
    # by setting subprocess_cwd in config (e.g. to str(Path.home())).
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


def _call_anthropic_sdk(system_prompt: str, user_message: str, config: dict) -> str:
    try:
        import anthropic
    except ImportError:
        raise BackendError(
            "'anthropic' package not installed. "
            "Run: pip install anthropic  (in the MCP venv: ~/.claude/mcp-venv/bin/pip install anthropic)"
        )

    backend = config.get("backend", DEFAULT_BACKEND)

    if backend == "bedrock":
        region = config.get("bedrock_region", "us-east-1")
        model = config.get("model", BEDROCK_DEFAULT_MODEL)
        client = anthropic.AnthropicBedrock(aws_region=region)
        print(f"[extract_beats] Using Bedrock backend (region={region}, model={model})", file=sys.stderr)
    else:  # "anthropic"
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise BackendError(
                "ANTHROPIC_API_KEY is not set. "
                "Export it in your environment or switch to backend=claude-cli / bedrock in knowledge.json."
            )
        model = config.get("model", DIRECT_DEFAULT_MODEL)
        client = anthropic.Anthropic()
        print(f"[extract_beats] Using Anthropic API backend (model={model})", file=sys.stderr)

    try:
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
    except Exception as e:
        raise BackendError(f"API call failed ({type(e).__name__}): {e}")

    if not response.content:
        raise BackendError("API returned an empty content array.")

    block = response.content[0]
    if not hasattr(block, "text"):
        raise BackendError(
            f"API returned an unexpected content block type: {type(block).__name__}. "
            "Expected a text block."
        )

    output = block.text.strip()
    if not output:
        raise BackendError("API returned an empty response text.")
    return output


def call_model(system_prompt: str, user_message: str, config: dict) -> str:
    backend = config.get("backend", DEFAULT_BACKEND)
    if backend == "claude-cli":
        return _call_claude_cli(system_prompt, user_message, config)
    else:
        return _call_anthropic_sdk(system_prompt, user_message, config)


def extract_beats(transcript_text: str, config: dict, trigger: str, cwd: str) -> list[dict]:
    project_name = config.get("project_name", Path(cwd).name)

    # Truncate transcript if too long (keep tail — most recent content is most valuable)
    if len(transcript_text) > MAX_TRANSCRIPT_CHARS:
        transcript_text = "...[earlier content truncated]...\n\n" + transcript_text[-MAX_TRANSCRIPT_CHARS:]

    system_prompt = load_prompt("extract-beats-system.md")
    user_message = load_prompt("extract-beats-user.md").format_map({
        "project_name": project_name,
        "cwd": cwd,
        "trigger": trigger,
        "transcript": transcript_text,
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

VALID_TYPES = {
    # Beat schema (auto-extracted) — 5-type collapsed vocabulary
    "decision", "insight", "action", "problem", "reference",
    # Vault note types (human-authored via kg-file) — pass through without remapping
    "project", "note", "resource", "archived", "claude-context",
}
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
    """Grep vault for files related to a beat by tags and title keywords."""
    import subprocess

    terms = list(beat.get("tags", []))
    terms += [w for w in beat["title"].split() if len(w) >= 4][:5]
    terms = list(dict.fromkeys(terms))  # deduplicate, preserve order

    found: dict[str, float] = {}  # path → mtime
    for term in terms:
        result = subprocess.run(
            ["grep", "-r", "-l", "--include=*.md", "-i", term, vault_path],
            capture_output=True, text=True
        )
        for path in result.stdout.strip().splitlines():
            if path and path not in found:
                try:
                    found[path] = os.path.getmtime(path)
                except OSError:
                    pass

    # Sort by recency, return top N
    return sorted(found, key=found.get, reverse=True)[:max_results]


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
        claude_md_path = Path(vault_path) / "CLAUDE.md"
        vault_context = claude_md_path.read_text(encoding="utf-8")[:3000] if claude_md_path.exists() else \
            "File notes using human-readable names with spaces. Use ontology types: concept, insight, decision, problem, reference."

    # Search for related vault docs
    related_paths = search_vault(beat, vault_path)
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

    # Build autofile-specific config: support a separate model for filing decisions
    backend = config.get("backend", DEFAULT_BACKEND)
    if "autofile_model" in config:
        autofile_config = dict(config)
        if backend == "claude-cli":
            autofile_config["claude_model"] = config["autofile_model"]
        else:
            autofile_config["model"] = config["autofile_model"]
        effective_model = config["autofile_model"]
    else:
        autofile_config = config
        if backend == "claude-cli":
            effective_model = config.get("claude_model", CLI_DEFAULT_MODEL)
        elif backend == "bedrock":
            effective_model = config.get("model", BEDROCK_DEFAULT_MODEL)
        else:
            effective_model = config.get("model", DIRECT_DEFAULT_MODEL)
    print(f"[extract_beats] autofile: using {effective_model}", file=sys.stderr)

    try:
        raw = call_model(system_prompt, user_message, autofile_config)
    except BackendError as e:
        print(f"[extract_beats] autofile: backend error, falling back to staging: {e}", file=sys.stderr)
        return write_beat(beat, config, session_id, cwd, now)
    if not raw:
        # Fall back to staging
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
        # Handle collisions — prepend number so the canonical name is unmodified
        base = output_path
        counter = 2
        while output_path.exists():
            output_path = base.parent / f"{counter} {base.name}"
            counter += 1
        output_path.write_text(content, encoding="utf-8")
        print(f"[extract_beats] autofile: created {output_path}", file=sys.stderr)
        return output_path

    else:
        print(f"[extract_beats] autofile: unknown action '{action}', falling back", file=sys.stderr)
        return write_beat(beat, config, session_id, cwd, now)


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

    # Build wikilinks for each written file
    links = []
    for path in written_paths:
        rel = os.path.relpath(path, vault)
        stem = path.stem
        links.append(f"- [[{rel}|{stem}]]")
    links_block = "\n".join(links) if links else "- (none)"

    session_block = (
        f"\n## Session {session_id[:8]} — {project_name}\n\n"
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
    parser.add_argument("--trigger", default="auto", choices=["auto", "manual", "session-end"], help="Compaction trigger type")
    parser.add_argument("--cwd", required=True, help="Working directory of the Claude Code session")
    args = parser.parse_args()

    if not args.transcript and not args.beats_json:
        print("[extract_beats] Provide --transcript or --beats-json.", file=sys.stderr)
        sys.exit(1)

    config = resolve_config(args.cwd)
    autofile_enabled = config.get("autofile", False)
    journal_enabled = config.get("daily_journal", False)

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
        transcript_text = parse_transcript(args.transcript)

        if not transcript_text.strip():
            print("[extract_beats] Transcript is empty or has no user/assistant turns. Nothing to extract.", file=sys.stderr)
            sys.exit(0)

        print("[extract_beats] Calling Claude API to extract beats...", file=sys.stderr)
        try:
            beats = extract_beats(transcript_text, config, args.trigger, args.cwd)
        except BackendError as e:
            print(f"[extract_beats] Backend error: {e}", file=sys.stderr)
            sys.exit(0)

    if not beats:
        print("[extract_beats] No beats extracted.", file=sys.stderr)
        sys.exit(0)

    now = datetime.now(timezone.utc)
    written = []

    # Cache vault CLAUDE.md once for the whole autofile run (avoids N disk reads for N beats)
    vault_context = None
    if autofile_enabled:
        vault = Path(config["vault_path"])
        claude_md_path = vault / "CLAUDE.md"
        if claude_md_path.exists():
            vault_context = claude_md_path.read_text(encoding="utf-8")[:3000]
        else:
            vault_context = "File notes using human-readable names with spaces. Use ontology types: concept, insight, decision, problem, reference."

    for beat in beats:
        try:
            if autofile_enabled:
                path = autofile_beat(beat, config, args.session_id, args.cwd, now, vault_context=vault_context)
            else:
                path = write_beat(beat, config, args.session_id, args.cwd, now)
            if path:
                written.append(path)
                print(f"[extract_beats] Wrote: {path}", file=sys.stderr)
        except Exception as e:
            print(f"[extract_beats] Failed on '{beat.get('title', '?')}': {e}", file=sys.stderr)

    if journal_enabled and written:
        project_name = config.get("project_name", Path(args.cwd).name)
        write_journal_entry(written, config, args.session_id, project_name, now)

    print(f"[extract_beats] Done. {len(written)} beat(s) written.", file=sys.stderr)


if __name__ == "__main__":
    main()
