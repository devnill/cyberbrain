"""
conftest.py — shared fixtures and helpers for the cyberbrain test suite.
"""

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

# Ensure the repo root is on sys.path so `import extractors.extract_beats` works
REPO_ROOT = Path(__file__).parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_vault(tmp_path):
    """Create a temporary vault directory with the minimum required structure."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / ".obsidian").mkdir()
    (vault / "AI" / "Claude-Sessions").mkdir(parents=True)
    return vault


@pytest.fixture
def temp_home(tmp_path, monkeypatch):
    """
    Create a temporary home directory and redirect Path.home() and the
    GLOBAL_CONFIG_PATH constant to point into it.
    """
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


@pytest.fixture
def global_config(temp_vault, temp_home):
    """
    Write a valid global config to the temporary home directory.
    Returns the config dict.
    """
    config_dir = temp_home / ".claude"
    config_dir.mkdir(parents=True, exist_ok=True)
    config = {
        "vault_path": str(temp_vault),
        "inbox": "AI/Claude-Sessions",
        "backend": "claude-code",
        "model": "claude-haiku-4-5",
        "claude_timeout": 30,
        "autofile": False,
        "daily_journal": False,
    }
    config_path = config_dir / "cyberbrain.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    return config


@pytest.fixture
def sample_beats():
    """Load the sample beats fixture from disk."""
    return json.loads((FIXTURES_DIR / "sample_llm_response_beats.json").read_text())


@pytest.fixture
def sample_autofile_response():
    """Load the sample autofile LLM response fixture from disk."""
    return json.loads((FIXTURES_DIR / "sample_llm_response_autofile.json").read_text())


@pytest.fixture
def sample_transcript_path():
    """Return the path to the sample transcript fixture."""
    return str(FIXTURES_DIR / "sample_transcript.jsonl")


@pytest.fixture
def fixed_now():
    """A fixed datetime for deterministic test output."""
    return datetime(2026, 3, 1, 14, 32, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Helper utilities available to tests
# ---------------------------------------------------------------------------

def make_beat(
    title="Test Beat",
    beat_type="insight",
    scope="general",
    summary="A test beat summary.",
    tags=None,
    body="## Test\n\nTest body.",
):
    """Construct a minimal beat dict for use in tests."""
    return {
        "title": title,
        "type": beat_type,
        "scope": scope,
        "summary": summary,
        "tags": tags or ["test", "fixture"],
        "body": body,
    }
