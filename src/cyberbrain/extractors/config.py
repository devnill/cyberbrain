"""
config.py

Global and per-project configuration loading, plus prompt file loading.
"""

import json
import sys
from pathlib import Path
from typing import TypedDict

from cyberbrain.extractors.state import config_path as _config_path_fn


def __getattr__(name: str):  # noqa: N807 — PEP 562 lazy module attributes
    if name == "GLOBAL_CONFIG_PATH":
        return _config_path_fn()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


PROJECT_CONFIG_NAME = "cyberbrain.local.json"
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

REQUIRED_GLOBAL_FIELDS = ["vault_path", "inbox"]


class ConfigError(Exception):
    """Raised when the global config is missing or invalid."""


class CyberbrainConfig(TypedDict, total=False):
    vault_path: str
    inbox: str
    backend: str
    model: str
    claude_timeout: int
    autofile: bool
    daily_journal: bool
    journal_folder: str
    journal_name: str
    proactive_recall: bool
    working_memory_folder: str
    working_memory_review_days: int
    consolidation_log: str
    consolidation_log_enabled: bool
    trash_folder: str
    search_backend: str
    embedding_model: str
    desktop_capture_mode: str
    working_memory_ttl: int
    quality_gate_enabled: bool
    restructure_model: str
    recall_model: str
    enrich_model: str
    review_model: str
    judge_model: str
    autofile_model: str
    index_refresh_interval: int
    uncertain_filing_behavior: str
    uncertain_filing_threshold: float
    project_name: str
    vault_folder: str
    ollama_url: str
    bedrock_region: str
    claude_path: str
    search_db_path: str


def load_global_config() -> CyberbrainConfig:
    import cyberbrain.extractors.config as _self

    _cfg_path = (
        _self.GLOBAL_CONFIG_PATH
    )  # goes through __getattr__ or test-patched attribute
    if not _cfg_path.exists():
        raise ConfigError(
            f"Cyberbrain config not found at {_cfg_path}. "
            "Run /cyberbrain:config in Claude Code to set up."
        )

    with open(_cfg_path) as f:
        config = json.load(f)

    missing = [k for k in REQUIRED_GLOBAL_FIELDS if not config.get(k)]
    if missing:
        raise ConfigError(
            f"Cyberbrain config at {_cfg_path} is missing required fields: {missing}. "
            "Run /cyberbrain:config in Claude Code to reconfigure."
        )

    vault_path = Path(config["vault_path"]).expanduser().resolve()

    # Reject placeholder or non-existent paths
    if (
        str(config["vault_path"]) == "/path/to/your/ObsidianVault"
        or not vault_path.exists()
    ):
        raise ConfigError(
            f"vault_path '{config['vault_path']}' is a placeholder or does not exist. "
            "Run /cyberbrain:config in Claude Code to set your real vault path."
        )

    # Reject home directory or filesystem root — indicates misconfiguration
    home = Path.home().resolve()
    root = Path("/").resolve()
    if vault_path == home or vault_path == root:
        raise ConfigError(
            "vault_path must not be your home directory or filesystem root. "
            "Run /cyberbrain:config in Claude Code to reconfigure."
        )

    config["vault_path"] = str(vault_path)
    return config  # type: ignore[return-value]


def find_project_config(cwd: str) -> dict[str, object]:
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


def resolve_config(cwd: str) -> CyberbrainConfig:
    global_cfg = load_global_config()
    project_cfg = find_project_config(cwd)
    return {**global_cfg, **project_cfg}  # type: ignore[return-value]


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
