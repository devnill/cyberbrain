"""
config.py

Global and per-project configuration loading, plus prompt file loading.
"""

import json
import sys
from pathlib import Path


GLOBAL_CONFIG_PATH = Path.home() / ".claude" / "cyberbrain" / "config.json"
PROJECT_CONFIG_NAME = "cyberbrain.local.json"
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

REQUIRED_GLOBAL_FIELDS = ["vault_path", "inbox"]


def load_global_config() -> dict:
    if not GLOBAL_CONFIG_PATH.exists():
        print(
            f"[extract_beats] Global config not found at {GLOBAL_CONFIG_PATH}. "
            "Create it with vault_path and inbox.",
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
    """Walk up from cwd looking for .claude/cyberbrain.local.json."""
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
