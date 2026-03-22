"""
conftest.py — shared fixtures and helpers for the cyberbrain test suite.
"""

import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent

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
    return datetime(2026, 3, 1, 14, 32, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Helper utilities available to tests
# ---------------------------------------------------------------------------


def _clear_module_cache(modules: list) -> None:
    """Remove the given module names from sys.modules so subsequent imports get a fresh copy.

    Several test files must control which version of a module (real or mock) is active
    at the time their imports are executed.  Python caches every successful import in
    sys.modules, so the *first* test file that imports cyberbrain.mcp.shared (or any
    other shared module) owns the cached object for the rest of the process.

    Calling this helper before an import forces Python to re-execute the module, which
    lets the test file inject its own mocks *before* the module binds its dependencies.

    Args:
        modules: List of fully-qualified module names to evict (e.g.
                 ["cyberbrain.mcp.shared", "cyberbrain.mcp.tools.reindex"]).
                 Names that are not currently in sys.modules are silently skipped.
    """
    for name in modules:
        sys.modules.pop(name, None)


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
    from cyberbrain.extractors.search_backends import SearchResult

    def _make(path="/vault/Note.md", title="Test Note", score=1.0, **kwargs):
        return SearchResult(path=path, title=title, score=score, **kwargs)

    return _make


# ---------------------------------------------------------------------------
# --affected-only: run only tests touched by recently changed source files
# ---------------------------------------------------------------------------


def pytest_addoption(parser):
    parser.addoption(
        "--affected-only",
        action="store_true",
        default=False,
        help="Run only tests affected by changed files",
    )


def pytest_configure(config):
    if config.getoption("--affected-only", default=False):
        import subprocess

        from _dependency_map import TestMapper

        # Get changed files from git
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD~1"], capture_output=True, text=True
        )
        changed = {Path(f) for f in result.stdout.splitlines() if f.endswith(".py")}

        # Map to tests
        mapper = TestMapper()
        mapper.build()

        affected = set()
        for src in changed:
            affected.update(mapper.get_tests_for(src))

        if affected:
            config.args = sorted(affected)
            config.option.verbose = 0
            config.option.tbstyle = "no"
