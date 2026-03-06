"""
conftest.py — shared fixtures and helpers for the cyberbrain test suite.
"""

import json
import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Ensure the repo root is on sys.path so `import extractors.extract_beats` works
REPO_ROOT = Path(__file__).parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Ensure the extractors/ directory is on sys.path so `import search_backends` works
EXTRACTORS_DIR = REPO_ROOT / "extractors"
if str(EXTRACTORS_DIR) not in sys.path:
    sys.path.insert(0, str(EXTRACTORS_DIR))

# Ensure the mcp/ directory is on sys.path for tool module imports
MCP_DIR = REPO_ROOT / "mcp"
if str(MCP_DIR) not in sys.path:
    sys.path.insert(0, str(MCP_DIR))

# ---------------------------------------------------------------------------
# Shared extract_beats mock — installed ONCE before any test module imports it.
#
# All test files that need to mock extract_beats (test_mcp_server.py,
# test_extract_file_tools.py, test_recall_read_tools.py) must use the SAME
# BackendError class, otherwise `except BackendError` in the tool code won't
# catch the test's side_effect exception.
#
# Installing here in conftest.py (which runs before any test module) ensures
# there is exactly one BackendError class across the whole test session.
# ---------------------------------------------------------------------------


class _SharedBackendError(Exception):
    """Shared BackendError used by all MCP tool tests.

    This must be a common base for any BackendError class used by individual
    test files. test_mcp_server.py creates its own `_BackendError(Exception)`
    and uses it as a side_effect. For `except BackendError` in the tool code
    to catch it, `BackendError` must be a superclass. Using `Exception` as a
    shared base ensures any `_BackendError(Exception)` is caught.
    """
    pass


if "extract_beats" not in sys.modules:
    _shared_mock_eb = MagicMock()
    # Use Exception as BackendError so any exception subclassing Exception is caught
    # by the `except BackendError` clause in tool code. This is safe for tests.
    _shared_mock_eb.BackendError = Exception
    _shared_mock_eb.RUNS_LOG_PATH = "/tmp/fake-runs.log"
    _shared_mock_eb.resolve_config = MagicMock(return_value={
        "vault_path": "/tmp/test_vault",
        "inbox": "AI/Claude-Sessions",
        "backend": "claude-code",
        "model": "claude-haiku-4-5",
        "autofile": False,
        "daily_journal": False,
    })
    _shared_mock_eb.parse_jsonl_transcript = MagicMock(return_value="User: hello\nAssistant: hi")
    _shared_mock_eb.extract_beats = MagicMock(return_value=[])
    _shared_mock_eb.write_beat = MagicMock()
    _shared_mock_eb.autofile_beat = MagicMock()
    _shared_mock_eb.write_journal_entry = MagicMock()
    _shared_mock_eb._call_claude_code = MagicMock(return_value="synthesis result")
    sys.modules["extract_beats"] = _shared_mock_eb

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


# ---------------------------------------------------------------------------
# New shared fixtures for search and KGE tests
# ---------------------------------------------------------------------------

@pytest.fixture
def vault_with_notes(temp_vault):
    """Creates temp_vault with 3 pre-written .md notes for relation/search tests."""
    notes = [
        ("JWT Authentication.md", "decision", ["jwt", "auth"]),
        ("Postgres Connection Pool.md", "problem", ["postgres", "database"]),
        ("Python Subprocess Encoding.md", "problem", ["python", "subprocess"]),
    ]
    inbox = temp_vault / "AI" / "Claude-Sessions"
    inbox.mkdir(parents=True, exist_ok=True)
    for filename, note_type, tags in notes:
        path = inbox / filename
        path.write_text(
            f"""---
id: {uuid.uuid4()}
type: {note_type}
title: "{filename[:-3]}"
tags: {json.dumps(tags)}
related: []
summary: "Summary of {filename[:-3]}"
---

## {filename[:-3]}

Body content for {filename[:-3]}.
""",
            encoding="utf-8",
        )
    return temp_vault


@pytest.fixture
def fts5_db_path(tmp_path):
    """Returns a path for a temporary FTS5 SQLite database."""
    return str(tmp_path / "test-search.db")


@pytest.fixture
def mock_search_result():
    """Returns a factory for SearchResult objects."""
    from search_backends import SearchResult

    def _make(path="/vault/Note.md", title="Test Note", score=1.0, **kwargs):
        return SearchResult(path=path, title=title, score=score, **kwargs)

    return _make
