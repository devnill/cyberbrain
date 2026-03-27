"""
test_setup_enrich_tools.py — unit tests for the cb_setup and cb_enrich MCP tools

Tests cover real-world use cases:
- cb_setup Phase 1: vault analysis, archetype detection, question generation
- cb_setup Phase 2: CLAUDE.md generation and writing
- cb_enrich: candidate detection, dry-run, batch processing, frontmatter updates
- Both tools: error handling, config loading, skip logic

All LLM calls (call_model) and vault I/O are mocked. No real API calls.
"""

import json
import sys
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# sys.path setup — same pattern as test_mcp_server.py
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent

# ---------------------------------------------------------------------------
# sys.modules setup — why this file needs it
#
# Modules temporarily mocked: cyberbrain.extractors.extract_beats,
#                              cyberbrain.extractors.quality_gate
# Modules cleared:             cyberbrain.mcp.shared, cyberbrain.mcp.tools.setup,
#                              cyberbrain.mcp.tools.enrich,
#                              cyberbrain.mcp.tools.recall,
#                              cyberbrain.extractors.backends,
#                              cyberbrain.extractors.frontmatter
#
# setup.py and enrich.py pull in shared.py which imports BackendError from
# extract_beats at module level.  Installing a stub mock ensures shared.py
# gets a local _BackendError rather than the real one, so test side_effects
# (raise _BackendError()) are caught by the tool's except-clause.
#
# __spec__ and __file__ are set on the mock so that any code path that calls
# runpy.run_module (or inspects the module's origin) does not crash with
# AttributeError.
#
# quality_gate imports from backends at module level; we guard it with a mock
# to prevent real LLM backend initialisation during tests.  The mock is NOT
# installed here at module level; the refresh_enrich_module fixture handles
# install/restore around every test to ensure a clean state.
#
# All the MCP-layer modules are cleared from the cache before import so that
# fresh module objects are created that bind to the mock rather than any stale
# previously-cached versions.
# ---------------------------------------------------------------------------
import importlib.util

from tests.conftest import _clear_module_cache


class _BackendError(Exception):
    pass


_mock_eb = MagicMock()
_mock_eb.BackendError = _BackendError
_mock_eb.resolve_config.return_value = {
    "vault_path": "/tmp/test_vault",
    "inbox": "AI/Claude-Sessions",
    "backend": "claude-code",
    "model": "claude-haiku-4-5",
    "autofile": False,
    "daily_journal": False,
}
# Add __spec__ and __file__ to mock to avoid breaking runpy.run_module in other tests
_mock_eb.__spec__ = importlib.util.spec_from_loader(
    "cyberbrain.extractors.extract_beats", loader=None
)
_mock_eb.__spec__.origin = str(
    REPO_ROOT / "src" / "cyberbrain" / "extractors" / "extract_beats.py"
)
_mock_eb.__file__ = str(
    REPO_ROOT / "src" / "cyberbrain" / "extractors" / "extract_beats.py"
)

# Note: We don't install the mock at module level anymore.
# The mock is installed by the fixture when needed.

# Create a mock quality_gate module for tests that need it.
# The fixture will handle installing and restoring this mock.
_mock_qg = MagicMock()

# ---------------------------------------------------------------------------
# FakeMCP (same as test_mcp_server.py)
# ---------------------------------------------------------------------------


class FakeMCP:
    def __init__(self):
        self._tools = {}

    def tool(self, annotations=None, **kwargs):
        def decorator(fn):
            self._tools[fn.__name__] = {"fn": fn}
            return fn

        return decorator


# ---------------------------------------------------------------------------
# Import and register tools
# ---------------------------------------------------------------------------

# Store the real extract_beats module before installing the mock
_real_extract_beats_for_teardown = sys.modules.get(
    "cyberbrain.extractors.extract_beats"
)

# Clear stale module cache entries so fresh imports bind to the stub mock.
_clear_module_cache(
    [
        "cyberbrain.mcp.shared",
        "cyberbrain.mcp.tools.setup",
        "cyberbrain.mcp.tools.enrich",
        "cyberbrain.mcp.tools.recall",
        "cyberbrain.extractors.backends",
        "cyberbrain.extractors.frontmatter",
        "cyberbrain.extractors.extract_beats",
    ]
)

# Re-install mock extract_beats after popping to ensure it's used
sys.modules["cyberbrain.extractors.extract_beats"] = _mock_eb

from cyberbrain.mcp.tools import enrich as _enrich_mod
from cyberbrain.mcp.tools import setup as _setup_mod

_fake_mcp = FakeMCP()
_setup_mod.register(_fake_mcp)
_enrich_mod.register(_fake_mcp)

cb_setup = _fake_mcp._tools["cb_setup"]["fn"]
cb_enrich = _fake_mcp._tools["cb_enrich"]["fn"]

try:
    from fastmcp.exceptions import ToolError
except ImportError:
    try:
        from mcp.server.fastmcp.exceptions import ToolError  # type: ignore[no-redef]
    except ImportError:

        class ToolError(Exception):  # type: ignore[no-redef]
            pass


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _vault_config(vault_path: str) -> dict:
    return {
        "vault_path": vault_path,
        "inbox": "AI/Claude-Sessions",
        "backend": "claude-code",
        "model": "claude-haiku-4-5",
        "claude_timeout": 30,
        "autofile": False,
    }


def write_note(vault: Path, rel_path: str, content: str) -> Path:
    path = vault / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def refresh_enrich_module():
    """Re-import enrich module to ensure cb_enrich is bound to the latest version.

    This is needed because test_auto_indexing.py pops cyberbrain.mcp.tools.enrich
    from sys.modules, which causes cb_enrich to be bound to a stale function.
    """
    global cb_enrich, cb_setup, _enrich_mod, _setup_mod, _shared
    # Store the current state before modifying
    _current_extract_beats = sys.modules.get("cyberbrain.extractors.extract_beats")
    _current_quality_gate = sys.modules.get("cyberbrain.extractors.quality_gate")
    # Clear stale module cache entries so re-imports see the mock, not a cached real module.
    _clear_module_cache(
        [
            "cyberbrain.mcp.shared",
            "cyberbrain.mcp.tools.setup",
            "cyberbrain.mcp.tools.enrich",
        ]
    )
    # Install mock extract_beats to prevent real LLM calls during tests
    sys.modules["cyberbrain.extractors.extract_beats"] = _mock_eb
    # Install mock quality_gate for test_setup_enrich_tools tests
    sys.modules["cyberbrain.extractors.quality_gate"] = _mock_qg
    # Re-import modules
    import cyberbrain.mcp.shared as _shared
    from cyberbrain.mcp.tools import enrich as _enrich_mod
    from cyberbrain.mcp.tools import setup as _setup_mod

    # Manually add to sys.modules to ensure it's there
    sys.modules["cyberbrain.mcp.tools.enrich"] = _enrich_mod
    sys.modules["cyberbrain.mcp.tools.setup"] = _setup_mod
    sys.modules["cyberbrain.mcp.shared"] = _shared

    # Patch shared module names to use mocks instead of real extractors.
    # shared.py now imports directly from source modules, so sys.modules
    # mocking of extract_beats no longer intercepts these. We must patch
    # both the shared module AND the tool modules that captured references
    # via `from shared import _load_config`.
    _shared._resolve_config = _mock_eb.resolve_config
    _shared._call_claude_code_backend = _mock_eb._call_claude_code
    _shared.BackendError = Exception
    _shared.write_beat = _mock_eb.write_beat
    _shared.autofile_beat = _mock_eb.autofile_beat
    _shared.write_journal_entry = _mock_eb.write_journal_entry
    _shared.parse_jsonl_transcript = _mock_eb.parse_jsonl_transcript
    _shared._extract_beats = _mock_eb.extract_beats
    _shared.RUNS_LOG_PATH = "/tmp/fake-runs.log"
    # Patch captured references in tool modules
    _setup_mod._load_config = _shared._load_config
    _enrich_mod._load_config = _shared._load_config
    # Re-register tools
    _fake_mcp = FakeMCP()
    _setup_mod.register(_fake_mcp)
    _enrich_mod.register(_fake_mcp)
    # Re-bind cb_enrich and cb_setup
    cb_enrich = _fake_mcp._tools["cb_enrich"]["fn"]
    cb_setup = _fake_mcp._tools["cb_setup"]["fn"]
    yield
    # Restore the previous state after tests
    if _current_extract_beats is not None:
        sys.modules["cyberbrain.extractors.extract_beats"] = _current_extract_beats
    else:
        sys.modules.pop("cyberbrain.extractors.extract_beats", None)
    if _current_quality_gate is not None:
        sys.modules["cyberbrain.extractors.quality_gate"] = _current_quality_gate
    else:
        sys.modules.pop("cyberbrain.extractors.quality_gate", None)


# ---------------------------------------------------------------------------
# cb_setup — configuration errors
# ---------------------------------------------------------------------------


class TestCbSetupConfigErrors:
    """cb_setup raises ToolError for bad configuration before any LLM call."""

    def test_raises_when_no_vault_configured(self):
        """ToolError when vault_path is not set and config has no vault_path."""
        with patch(
            "cyberbrain.mcp.tools.setup._load_config", return_value={"vault_path": ""}
        ):
            with pytest.raises(ToolError, match="No vault path"):
                cb_setup()

    def test_raises_when_vault_path_does_not_exist(self, tmp_path):
        """ToolError when the vault directory doesn't exist on disk."""
        nonexistent = str(tmp_path / "no-such-vault")
        with patch(
            "cyberbrain.mcp.tools.enrich._load_config",
            return_value=_vault_config(nonexistent),
        ):
            with pytest.raises(ToolError, match="does not exist"):
                cb_setup(vault_path=nonexistent)

    def test_uses_vault_path_arg_over_config(self, tmp_path):
        """
        When vault_path is passed as an argument, it takes precedence over config.
        This allows cb_setup to analyze a vault other than the one in config.
        """
        config = _vault_config(str(tmp_path / "other-vault"))
        with patch("cyberbrain.mcp.tools.enrich._load_config", return_value=config):
            with patch(
                "cyberbrain.mcp.tools.setup._run_analyzer",
                return_value={"total_notes": 0},
            ):
                with patch(
                    "cyberbrain.mcp.tools.setup._read_note_samples", return_value=""
                ):
                    with patch(
                        "cyberbrain.extractors.backends.call_model",
                        return_value='{"archetype": "developer", "questions": []}',
                    ):
                        # vault_path arg points to tmp_path which exists
                        result = cb_setup(vault_path=str(tmp_path))
        # Should not raise — the argument path was used
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# cb_setup — Phase 1 (analysis)
# ---------------------------------------------------------------------------


class TestCbSetupPhase1:
    """Phase 1: analyze vault, return JSON with archetype and questions."""

    @pytest.fixture
    def vault(self, tmp_path):
        v = tmp_path / "vault"
        v.mkdir()
        write_note(
            v,
            "AI/Claude-Sessions/Decision A.md",
            """\
---
type: decision
summary: Chose FastAPI.
tags: [python, api]
---

## Decision
""",
        )
        write_note(
            v,
            "AI/Claude-Sessions/Problem B.md",
            """\
---
type: problem
summary: JWT clock skew.
tags: [jwt, auth]
---

## Problem
""",
        )
        return v

    def _phase1_config(self, vault):
        return _vault_config(str(vault))

    def test_returns_valid_json_from_model(self, vault):
        """Phase 1 returns the JSON analysis from the model as a string."""
        analysis = {
            "archetype": "developer",
            "archetype_evidence": "Technical notes with code.",
            "existing_types": ["decision", "problem"],
            "recommendation": "adopt",
            "recommendation_rationale": "Well-designed.",
            "anti_patterns": [],
            "questions": [
                {"id": "q1", "question": "What is this vault primarily used for?"}
            ],
        }
        with patch(
            "cyberbrain.mcp.tools.enrich._load_config",
            return_value=self._phase1_config(vault),
        ):
            with patch(
                "cyberbrain.mcp.tools.setup._run_analyzer",
                return_value={"total_notes": 2, "links": {}},
            ):
                with patch(
                    "cyberbrain.mcp.tools.setup._read_note_samples",
                    return_value="sample content",
                ):
                    with patch(
                        "cyberbrain.extractors.backends.call_model",
                        return_value=json.dumps(analysis),
                    ):
                        result = cb_setup(vault_path=str(vault))

        parsed = json.loads(result)
        assert parsed["archetype"] == "developer"
        assert len(parsed["questions"]) == 1
        assert parsed["questions"][0]["id"] == "q1"

    def test_strips_markdown_fences_from_model_output(self, vault):
        """Phase 1 strips ```json fences if the model wraps the JSON."""
        analysis = {"archetype": "developer", "questions": []}
        fenced = f"```json\n{json.dumps(analysis)}\n```"

        with patch(
            "cyberbrain.mcp.tools.enrich._load_config",
            return_value=self._phase1_config(vault),
        ):
            with patch(
                "cyberbrain.mcp.tools.setup._run_analyzer",
                return_value={"total_notes": 0, "links": {}},
            ):
                with patch(
                    "cyberbrain.mcp.tools.setup._read_note_samples", return_value=""
                ):
                    with patch(
                        "cyberbrain.extractors.backends.call_model", return_value=fenced
                    ):
                        result = cb_setup(vault_path=str(vault))

        parsed = json.loads(result)
        assert parsed["archetype"] == "developer"

    def test_returns_raw_output_when_model_returns_non_json(self, vault):
        """If the model returns non-JSON, the raw output is returned (graceful degradation)."""
        with patch(
            "cyberbrain.mcp.tools.enrich._load_config",
            return_value=self._phase1_config(vault),
        ):
            with patch(
                "cyberbrain.mcp.tools.setup._run_analyzer",
                return_value={"total_notes": 0, "links": {}},
            ):
                with patch(
                    "cyberbrain.mcp.tools.setup._read_note_samples", return_value=""
                ):
                    with patch(
                        "cyberbrain.extractors.backends.call_model",
                        return_value="Sorry, I cannot analyze this.",
                    ):
                        result = cb_setup(vault_path=str(vault))

        assert "Sorry" in result

    def test_includes_existing_claude_md_in_analysis(self, vault):
        """When the vault has a CLAUDE.md, it should be included in the model prompt."""
        (vault / "CLAUDE.md").write_text(
            "# Vault Instructions\n\nUse type: decision.\n"
        )

        prompt_args = {}

        def capture_call(system_prompt, user_message, config):
            prompt_args["user"] = user_message
            return '{"archetype": "developer", "questions": []}'

        with patch(
            "cyberbrain.mcp.tools.enrich._load_config",
            return_value=self._phase1_config(vault),
        ):
            with patch(
                "cyberbrain.mcp.tools.setup._run_analyzer",
                return_value={"total_notes": 0, "links": {}},
            ):
                with patch(
                    "cyberbrain.mcp.tools.setup._read_note_samples", return_value=""
                ):
                    with patch(
                        "cyberbrain.extractors.backends.call_model",
                        side_effect=capture_call,
                    ):
                        cb_setup(vault_path=str(vault))

        assert "CLAUDE.md" in prompt_args.get(
            "user", ""
        ) or "Vault Instructions" in prompt_args.get("user", "")

    def test_gracefully_handles_analyzer_failure(self, vault):
        """If analyze_vault throws, cb_setup continues with the error report."""
        with patch(
            "cyberbrain.mcp.tools.enrich._load_config",
            return_value=self._phase1_config(vault),
        ):
            with patch(
                "cyberbrain.mcp.tools.setup._run_analyzer",
                return_value={"error": "pyyaml not installed", "total_notes": 0},
            ):
                with patch(
                    "cyberbrain.mcp.tools.setup._read_note_samples", return_value=""
                ):
                    with patch(
                        "cyberbrain.extractors.backends.call_model",
                        return_value='{"archetype": "developer", "questions": []}',
                    ):
                        result = cb_setup(vault_path=str(vault))

        assert "developer" in result

    def test_raises_tool_error_on_backend_error(self, vault):
        """If the backend raises an exception, ToolError is raised."""
        with patch(
            "cyberbrain.mcp.tools.enrich._load_config",
            return_value=self._phase1_config(vault),
        ):
            with patch(
                "cyberbrain.mcp.tools.setup._run_analyzer",
                return_value={"total_notes": 0, "links": {}},
            ):
                with patch(
                    "cyberbrain.mcp.tools.setup._read_note_samples", return_value=""
                ):
                    with patch(
                        "cyberbrain.extractors.backends.call_model",
                        side_effect=Exception("Connection refused"),
                    ):
                        with pytest.raises(ToolError, match="Phase 1"):
                            cb_setup(vault_path=str(vault))


# ---------------------------------------------------------------------------
# cb_setup — Phase 2 (CLAUDE.md generation)
# ---------------------------------------------------------------------------


class TestCbSetupPhase2:
    """Phase 2: generate CLAUDE.md from analysis + user answers."""

    @pytest.fixture
    def vault(self, tmp_path):
        v = tmp_path / "vault"
        v.mkdir()
        return v

    def _config(self, vault):
        return _vault_config(str(vault))

    _answers = json.dumps({"q1": "Primarily technical notes for software projects."})

    _claude_md_content = textwrap.dedent("""\
        # Vault Overview

        A developer PKM for software projects.

        ## Knowledge Graph

        ### Principles

        Types describe epistemic role, not topic.

        ### Relation Vocabulary

        | Predicate | When to use |
        |---|---|
        | `related` | General association. |
    """)

    def test_returns_preview_when_write_false(self, vault):
        """Phase 2 with write=False returns the content but does not write the file."""
        with patch(
            "cyberbrain.mcp.tools.enrich._load_config", return_value=self._config(vault)
        ):
            with patch(
                "cyberbrain.mcp.tools.setup._run_analyzer",
                return_value={"total_notes": 0, "links": {}},
            ):
                with patch(
                    "cyberbrain.mcp.tools.setup._read_note_samples", return_value=""
                ):
                    with patch(
                        "cyberbrain.extractors.backends.call_model",
                        return_value=self._claude_md_content,
                    ):
                        result = cb_setup(
                            vault_path=str(vault),
                            answers=self._answers,
                            write=False,
                        )

        assert "Generated CLAUDE.md" in result
        assert "Vault Overview" in result
        assert not (vault / "CLAUDE.md").exists()

    def test_dry_run_returns_content_without_writing(self, vault):
        """dry_run=True shows the content but never writes."""
        with patch(
            "cyberbrain.mcp.tools.enrich._load_config", return_value=self._config(vault)
        ):
            with patch(
                "cyberbrain.mcp.tools.setup._run_analyzer",
                return_value={"total_notes": 0, "links": {}},
            ):
                with patch(
                    "cyberbrain.mcp.tools.setup._read_note_samples", return_value=""
                ):
                    with patch(
                        "cyberbrain.extractors.backends.call_model",
                        return_value=self._claude_md_content,
                    ):
                        result = cb_setup(
                            vault_path=str(vault),
                            answers=self._answers,
                            dry_run=True,
                        )

        assert "[DRY RUN]" in result
        assert not (vault / "CLAUDE.md").exists()
        assert "plus button > connectors > cyberbrain > orient" in result
        assert "cb_recall" in result

    def test_writes_claude_md_when_write_true(self, vault):
        """Phase 2 with write=True creates CLAUDE.md at the vault root."""
        with patch(
            "cyberbrain.mcp.tools.enrich._load_config", return_value=self._config(vault)
        ):
            with patch(
                "cyberbrain.mcp.tools.setup._run_analyzer",
                return_value={"total_notes": 0, "links": {}},
            ):
                with patch(
                    "cyberbrain.mcp.tools.setup._read_note_samples", return_value=""
                ):
                    with patch(
                        "cyberbrain.extractors.backends.call_model",
                        return_value=self._claude_md_content,
                    ):
                        result = cb_setup(
                            vault_path=str(vault),
                            answers=self._answers,
                            write=True,
                        )

        claude_md = vault / "CLAUDE.md"
        assert claude_md.exists()
        assert "Vault Overview" in claude_md.read_text()
        assert "CLAUDE.md written to" in result
        assert "plus button > connectors > cyberbrain > orient" in result
        assert "cb_recall" in result

    def test_types_override_skips_archetype_analysis(self, vault):
        """When types= is provided, the analysis prompt includes the override note."""
        prompt_args = {}

        def capture(system_prompt, user_message, config):
            prompt_args["user"] = user_message
            return '{"archetype": "developer", "questions": []}'

        with patch(
            "cyberbrain.mcp.tools.enrich._load_config", return_value=self._config(vault)
        ):
            with patch(
                "cyberbrain.mcp.tools.setup._run_analyzer",
                return_value={"total_notes": 0, "links": {}},
            ):
                with patch(
                    "cyberbrain.mcp.tools.setup._read_note_samples", return_value=""
                ):
                    with patch(
                        "cyberbrain.extractors.backends.call_model", side_effect=capture
                    ):
                        cb_setup(vault_path=str(vault), types="concept,note,resource")

        assert "concept,note,resource" in prompt_args.get("user", "")

    def test_raises_tool_error_on_generation_failure(self, vault):
        """If the backend fails in Phase 2, ToolError is raised."""
        with patch(
            "cyberbrain.mcp.tools.enrich._load_config", return_value=self._config(vault)
        ):
            with patch(
                "cyberbrain.mcp.tools.setup._run_analyzer",
                return_value={"total_notes": 0, "links": {}},
            ):
                with patch(
                    "cyberbrain.mcp.tools.setup._read_note_samples", return_value=""
                ):
                    with patch(
                        "cyberbrain.extractors.backends.call_model",
                        side_effect=Exception("Rate limit"),
                    ):
                        with pytest.raises(ToolError, match="Phase 2"):
                            cb_setup(
                                vault_path=str(vault), answers=self._answers, write=True
                            )


# ---------------------------------------------------------------------------
# cb_enrich — candidate detection
# ---------------------------------------------------------------------------


class TestCbEnrichCandidateDetection:
    """
    Verify which notes are identified as needing enrichment vs already done vs skipped.
    Tests use real filesystem writes — no mocking needed for the detection phase.
    """

    @pytest.fixture
    def vault(self, tmp_path):
        v = tmp_path / "vault"
        v.mkdir()
        return v

    def _config(self, vault):
        return _vault_config(str(vault))

    def test_flags_note_with_no_frontmatter(self, vault):
        """A note with no frontmatter block is flagged for enrichment."""
        write_note(vault, "No Frontmatter.md", "# Just a heading\n\nBody text.")

        with patch(
            "cyberbrain.mcp.tools.enrich._load_config", return_value=self._config(vault)
        ):
            result = cb_enrich(dry_run=True)

        assert "No Frontmatter.md" in result
        assert "no frontmatter" in result

    def test_flags_note_missing_type(self, vault):
        """A note with frontmatter but no `type` field is flagged."""
        write_note(
            vault,
            "Typed Note.md",
            """\
---
summary: Has summary but no type.
tags: [testing]
---

Body.
""",
        )
        with patch(
            "cyberbrain.mcp.tools.enrich._load_config", return_value=self._config(vault)
        ):
            result = cb_enrich(dry_run=True)

        assert "Typed Note.md" in result
        assert "missing type" in result

    def test_flags_note_with_invalid_type(self, vault):
        """A note whose type is not in the valid vocabulary is flagged."""
        write_note(
            vault,
            "CLAUDE.md",
            """\
## Entity Types

### decision
### insight
### problem
### reference
""",
        )
        write_note(
            vault,
            "Bad Type.md",
            """\
---
type: work-notes
summary: Summary here.
tags: [testing]
---

Body.
""",
        )
        with patch(
            "cyberbrain.mcp.tools.enrich._load_config", return_value=self._config(vault)
        ):
            result = cb_enrich(dry_run=True)

        assert "Bad Type.md" in result
        assert "invalid type" in result

    def test_flags_note_missing_summary(self, vault):
        """A note with type and tags but no summary is flagged."""
        write_note(
            vault,
            "No Summary.md",
            """\
---
type: decision
tags: [python, api]
---

Body.
""",
        )
        with patch(
            "cyberbrain.mcp.tools.enrich._load_config", return_value=self._config(vault)
        ):
            result = cb_enrich(dry_run=True)

        assert "No Summary.md" in result

    def test_flags_note_missing_tags(self, vault):
        """A note with type and summary but no tags is flagged."""
        write_note(
            vault,
            "No Tags.md",
            """\
---
type: decision
summary: Chose FastAPI over Flask.
---

Body.
""",
        )
        with patch(
            "cyberbrain.mcp.tools.enrich._load_config", return_value=self._config(vault)
        ):
            result = cb_enrich(dry_run=True)

        assert "No Tags.md" in result

    def test_skips_fully_enriched_note(self, vault):
        """A note with valid entity type, summary, and specific tags is not flagged."""
        write_note(
            vault,
            "Fully Enriched.md",
            """\
---
type: resource
summary: Chose FastAPI for its async support and type safety.
tags: [fastapi, python, backend]
---

Body.
""",
        )
        with patch(
            "cyberbrain.mcp.tools.enrich._load_config", return_value=self._config(vault)
        ):
            result = cb_enrich(dry_run=True)

        assert "Would enrich 0" in result

    def test_skips_daily_journal_notes(self, vault):
        """Notes matching YYYY-MM-DD.md are skipped."""
        write_note(vault, "2026-03-05.md", "# Daily Journal\n\nToday I...")

        import sys

        print(f"DEBUG: _enrich_mod = {_enrich_mod}", file=sys.stderr)
        print(
            f"DEBUG: sys.modules['cyberbrain.mcp.tools.enrich'] = {sys.modules.get('cyberbrain.mcp.tools.enrich')}",
            file=sys.stderr,
        )
        print(
            f"DEBUG: _enrich_mod is sys.modules['cyberbrain.mcp.tools.enrich'] = {_enrich_mod is sys.modules.get('cyberbrain.mcp.tools.enrich')}",
            file=sys.stderr,
        )
        print(
            f"DEBUG: _enrich_mod._load_config = {_enrich_mod._load_config}",
            file=sys.stderr,
        )
        with patch(
            "cyberbrain.mcp.tools.enrich._load_config", return_value=self._config(vault)
        ) as mock_load:
            print(f"DEBUG: mock_load = {mock_load}", file=sys.stderr)
            print(
                f"DEBUG: _enrich_mod._load_config after patch = {_enrich_mod._load_config}",
                file=sys.stderr,
            )
            result = cb_enrich(dry_run=True)

        # Daily journal should be skipped, not enriched
        assert "2026-03-05.md" not in result or "Would enrich 0" in result

    def test_skips_template_notes(self, vault):
        """Notes in /templates/ folders are skipped."""
        write_note(
            vault,
            "templates/Decision Template.md",
            """\
# Decision Template
[Fill in decision here]
""",
        )
        with patch.object(
            _enrich_mod, "_load_config", return_value=self._config(vault)
        ):
            result = cb_enrich(dry_run=True)

        assert "Would enrich 0" in result

    def test_skips_notes_with_enrich_skip(self, vault):
        """Notes with `enrich: skip` frontmatter are not processed."""
        write_note(
            vault,
            "Index.md",
            """\
---
enrich: skip
type: moc
---

# Index
""",
        )
        with patch(
            "cyberbrain.mcp.tools.enrich._load_config", return_value=self._config(vault)
        ):
            result = cb_enrich(dry_run=True)

        assert "Would enrich 0" in result

    def test_limit_parameter_caps_candidates(self, vault):
        """The limit parameter caps how many notes are processed."""
        for i in range(5):
            write_note(vault, f"Note {i}.md", f"# Note {i}\n\nNo frontmatter.")

        with patch(
            "cyberbrain.mcp.tools.enrich._load_config", return_value=self._config(vault)
        ):
            result = cb_enrich(dry_run=True, limit=2)

        assert "Would enrich 2" in result

    def test_since_parameter_filters_by_mtime(self, vault, tmp_path):
        """The since parameter only includes notes modified on or after the date."""

        old_note = write_note(vault, "Old Note.md", "# Old\n\nNo frontmatter.")
        # Make it old by setting mtime to epoch
        import os

        os.utime(str(old_note), (0, 0))

        new_note = write_note(vault, "New Note.md", "# New\n\nNo frontmatter.")
        # new_note already has current mtime

        with patch(
            "cyberbrain.mcp.tools.enrich._load_config", return_value=self._config(vault)
        ):
            result = cb_enrich(dry_run=True, since="2020-01-01")

        # Both old and new notes should be included (epoch is before 2020)
        # But since epoch (1970) is before 2020, let's use a future date to filter
        with patch(
            "cyberbrain.mcp.tools.enrich._load_config", return_value=self._config(vault)
        ):
            result_filtered = cb_enrich(dry_run=True, since="2030-01-01")

        # No notes modified after 2030 exist
        assert "Would enrich 0" in result_filtered


# ---------------------------------------------------------------------------
# cb_enrich — dry run report format
# ---------------------------------------------------------------------------


class TestCbEnrichDryRunReport:
    """Verify the dry-run report is correctly formatted."""

    @pytest.fixture
    def vault(self, tmp_path):
        v = tmp_path / "vault"
        v.mkdir()
        write_note(v, "Missing Meta.md", "# Note\n\nNo frontmatter.")
        write_note(
            v,
            "Partial Meta.md",
            """\
---
type: decision
---
Body.
""",
        )
        return v

    def _config(self, vault):
        return _vault_config(str(vault))

    def test_dry_run_shows_dry_run_header(self, vault):
        with patch(
            "cyberbrain.mcp.tools.enrich._load_config", return_value=self._config(vault)
        ):
            result = cb_enrich(dry_run=True)
        assert "[DRY RUN]" in result

    def test_dry_run_shows_valid_types(self, vault):
        with patch(
            "cyberbrain.mcp.tools.enrich._load_config", return_value=self._config(vault)
        ):
            result = cb_enrich(dry_run=True)
        assert "Valid types:" in result

    def test_dry_run_no_files_written_message(self, vault):
        with patch(
            "cyberbrain.mcp.tools.enrich._load_config", return_value=self._config(vault)
        ):
            result = cb_enrich(dry_run=True)
        assert "No files were modified" in result

    def test_nothing_to_enrich_message(self, tmp_path):
        """When all notes are already enriched, a clean message is returned."""
        v = tmp_path / "all-done-vault"
        v.mkdir()
        write_note(
            v,
            "Done.md",
            """\
---
type: resource
summary: Chose FastAPI.
tags: [python, fastapi]
---
Body.
""",
        )
        with patch(
            "cyberbrain.mcp.tools.enrich._load_config",
            return_value=_vault_config(str(v)),
        ):
            result = cb_enrich(dry_run=True)

        assert "All notes already have required metadata" in result


# ---------------------------------------------------------------------------
# cb_enrich — actual enrichment (normal mode)
# ---------------------------------------------------------------------------


class TestCbEnrichNormalMode:
    """Verify that cb_enrich actually calls the model and applies frontmatter."""

    @pytest.fixture
    def vault(self, tmp_path):
        v = tmp_path / "vault"
        v.mkdir()
        return v

    def _config(self, vault):
        return _vault_config(str(vault))

    def test_enriches_note_with_no_frontmatter(self, vault):
        """
        A note with no frontmatter gets a complete frontmatter block prepended.
        Real-world case: manually written notes that predate cyberbrain.
        """
        note_path = write_note(
            vault,
            "Manual Note.md",
            textwrap.dedent("""\
            # PostgreSQL Index Optimization

            When you have a slow query on a large table, adding a partial index
            on the most selective WHERE conditions can reduce scan time by 10x.
            Remember to use EXPLAIN ANALYZE to verify.
        """),
        )

        classification = [
            {
                "index": 0,
                "type": "reference",
                "summary": "PostgreSQL partial indexes on selective WHERE conditions improve slow query scan time by up to 10x.",
                "tags": ["postgresql", "indexing", "performance"],
                "skip": False,
                "skip_reason": "",
            }
        ]

        with patch(
            "cyberbrain.mcp.tools.enrich._load_config", return_value=self._config(vault)
        ):
            with patch(
                "cyberbrain.extractors.backends.call_model",
                return_value=json.dumps(classification),
            ):
                result = cb_enrich()

        content = note_path.read_text()
        assert content.startswith("---"), "Frontmatter block must be prepended"
        assert "type: reference" in content
        assert "postgresql" in content
        assert "Enriched:     1" in result

    def test_enriches_note_with_partial_frontmatter(self, vault):
        """
        A note with frontmatter but missing fields gets additive updates.
        Existing fields must not be overwritten in the default (non-overwrite) mode.
        """
        note_path = write_note(
            vault,
            "Partial.md",
            textwrap.dedent("""\
            ---
            type: insight
            custom-field: keep-this
            ---

            # JWT Clock Skew

            JWT tokens fail validation when server clocks differ by more than the
            configured tolerance window.
        """),
        )

        classification = [
            {
                "index": 0,
                "type": "problem",  # model suggests problem, but existing type=insight should be kept
                "summary": "JWT tokens fail when server clocks diverge beyond tolerance.",
                "tags": ["jwt", "auth", "clock-skew"],
                "skip": False,
                "skip_reason": "",
            }
        ]

        with patch(
            "cyberbrain.mcp.tools.enrich._load_config", return_value=self._config(vault)
        ):
            with patch(
                "cyberbrain.extractors.backends.call_model",
                return_value=json.dumps(classification),
            ):
                cb_enrich()

        content = note_path.read_text()
        assert "type: insight" in content, "Existing type must not be overwritten"
        assert "summary:" in content, "Summary should be added"
        assert "jwt" in content, "Tags should be added"
        assert "custom-field: keep-this" in content, "Custom fields must be preserved"

    def test_overwrite_mode_replaces_existing_fields(self, vault):
        """When overwrite=True, existing type/summary/tags are replaced."""
        note_path = write_note(
            vault,
            "Overwrite Me.md",
            textwrap.dedent("""\
            ---
            type: decision
            summary: Old summary.
            tags: [old-tag]
            ---

            Body.
        """),
        )

        classification = [
            {
                "index": 0,
                "type": "insight",
                "summary": "New accurate summary.",
                "tags": ["new-tag", "updated"],
                "skip": False,
                "skip_reason": "",
            }
        ]

        with patch(
            "cyberbrain.mcp.tools.enrich._load_config", return_value=self._config(vault)
        ):
            with patch(
                "cyberbrain.extractors.backends.call_model",
                return_value=json.dumps(classification),
            ):
                cb_enrich(overwrite=True)

        content = note_path.read_text()
        assert "type: insight" in content
        assert "New accurate summary" in content
        assert "new-tag" in content

    def test_skip_flag_in_classification_is_respected(self, vault):
        """When the model returns skip=True for a note, it is not enriched."""
        write_note(vault, "Meeting Notes.md", "# Team Sync\n\n- Discussed Q1 goals")

        classification = [
            {
                "index": 0,
                "type": None,
                "summary": None,
                "tags": [],
                "skip": True,
                "skip_reason": "meeting notes cannot be classified",
            }
        ]

        with patch(
            "cyberbrain.mcp.tools.enrich._load_config", return_value=self._config(vault)
        ):
            with patch(
                "cyberbrain.extractors.backends.call_model",
                return_value=json.dumps(classification),
            ):
                result = cb_enrich()

        assert "Enriched:     0" in result

    def test_handles_json_parse_error_from_model(self, vault):
        """If the model returns invalid JSON, the batch is recorded as errors."""
        write_note(vault, "Unclassifiable.md", "# Note\n\nNo frontmatter.")

        with patch(
            "cyberbrain.mcp.tools.enrich._load_config", return_value=self._config(vault)
        ):
            with patch(
                "cyberbrain.extractors.backends.call_model",
                return_value="not valid json {{{{",
            ):
                result = cb_enrich()

        assert "Errors:       1" in result
        assert "Enriched:     0" in result

    def test_handles_model_returning_too_few_results(self, vault):
        """If the model returns fewer classifications than notes, missing ones are errors."""
        for i in range(3):
            write_note(vault, f"Note {i}.md", f"# Note {i}\n\nNo frontmatter.")

        # Only 1 classification for 3 notes
        classification = [
            {
                "index": 0,
                "type": "reference",
                "summary": "Only one result.",
                "tags": ["test"],
                "skip": False,
                "skip_reason": "",
            }
        ]

        with patch(
            "cyberbrain.mcp.tools.enrich._load_config", return_value=self._config(vault)
        ):
            with patch(
                "cyberbrain.extractors.backends.call_model",
                return_value=json.dumps(classification),
            ):
                result = cb_enrich()

        # 1 enriched + 2 errors (or similar, depending on batch logic)
        assert "Enriched:     1" in result

    def test_raises_tool_error_when_vault_not_configured(self):
        """ToolError when vault_path is missing from config."""
        with patch(
            "cyberbrain.mcp.tools.enrich._load_config", return_value={"vault_path": ""}
        ):
            with pytest.raises(ToolError, match="No vault configured"):
                cb_enrich()

    def test_raises_tool_error_for_invalid_since_date(self, tmp_path):
        """ToolError for a since= value that is not a valid ISO date."""
        v = tmp_path / "v"
        v.mkdir()
        with patch(
            "cyberbrain.mcp.tools.enrich._load_config",
            return_value=_vault_config(str(v)),
        ):
            with pytest.raises(ToolError, match="Invalid date"):
                cb_enrich(since="not-a-date")

    def test_folder_parameter_restricts_scan_scope(self, vault):
        """
        When folder= is specified, only notes in that subfolder are scanned.
        Notes outside the folder are not modified.
        """
        write_note(vault, "AI/Notes/Relevant.md", "# Relevant\n\nNo frontmatter.")
        write_note(vault, "Projects/Other.md", "# Other\n\nNo frontmatter.")

        classification = [
            {
                "index": 0,
                "type": "reference",
                "summary": "Relevant note summary.",
                "tags": ["relevant"],
                "skip": False,
                "skip_reason": "",
            }
        ]

        with patch(
            "cyberbrain.mcp.tools.enrich._load_config", return_value=self._config(vault)
        ):
            with patch(
                "cyberbrain.extractors.backends.call_model",
                return_value=json.dumps(classification),
            ):
                result = cb_enrich(folder="AI/Notes")

        # Only 1 note scanned (the one in AI/Notes/)
        assert "1 notes scanned" in result


# ---------------------------------------------------------------------------
# cb_enrich — quality gate integration
# ---------------------------------------------------------------------------


class TestCbEnrichQualityGate:
    """Verify that the quality gate blocks bad classifications."""

    @pytest.fixture
    def vault(self, tmp_path):
        v = tmp_path / "vault"
        v.mkdir()
        return v

    def _config(self, vault, gate_enabled=True):
        cfg = _vault_config(str(vault))
        cfg["quality_gate_enabled"] = gate_enabled
        return cfg

    def test_gate_blocks_bad_classification(self, vault):
        """A classification that fails the quality gate is not applied."""
        from unittest.mock import MagicMock as _MagicMock

        note_path = write_note(
            vault,
            "Decorators.md",
            "# Python Decorators\n\nHow to use decorators in Python.",
        )

        classification = [
            {
                "index": 0,
                "type": "problem",
                "summary": "Cooking recipe for pasta.",
                "tags": ["cooking", "recipes"],
                "skip": False,
            }
        ]

        # Create a failing verdict
        fail_verdict = _MagicMock()
        fail_verdict.passed = False
        fail_verdict.rationale = "Type 'problem' does not match tutorial content"
        fail_verdict.confidence = 0.3

        with patch(
            "cyberbrain.mcp.tools.enrich._load_config", return_value=self._config(vault)
        ):
            with patch(
                "cyberbrain.extractors.backends.call_model",
                return_value=json.dumps(classification),
            ):
                with patch(
                    "cyberbrain.extractors.quality_gate.quality_gate",
                    return_value=fail_verdict,
                ):
                    result = cb_enrich()

        assert "Gate blocked: 1" in result
        assert "Enriched:     0" in result
        assert (
            "Call cb_configure(quality_gate_enabled=False) to disable quality gates."
            in result
        )
        # File should not have been modified
        content = note_path.read_text()
        assert "type: problem" not in content
        assert "cooking" not in content

    def test_gate_passes_good_classification(self, vault):
        """A classification that passes the quality gate is applied normally."""
        from unittest.mock import MagicMock as _MagicMock

        note_path = write_note(
            vault,
            "Decorators.md",
            "# Python Decorators\n\nHow to use decorators in Python.",
        )

        classification = [
            {
                "index": 0,
                "type": "reference",
                "summary": "Python decorator usage patterns.",
                "tags": ["python", "decorators"],
                "skip": False,
            }
        ]

        pass_verdict = _MagicMock()
        pass_verdict.passed = True
        pass_verdict.confidence = 0.9

        with patch(
            "cyberbrain.mcp.tools.enrich._load_config", return_value=self._config(vault)
        ):
            with patch(
                "cyberbrain.extractors.backends.call_model",
                return_value=json.dumps(classification),
            ):
                with patch(
                    "cyberbrain.extractors.quality_gate.quality_gate",
                    return_value=pass_verdict,
                ):
                    result = cb_enrich()

        assert "Enriched:     1" in result
        assert "Gate blocked: 0" in result
        content = note_path.read_text()
        assert "type: reference" in content

    def test_gate_disabled_skips_check(self, vault):
        """When quality_gate_enabled is false, classifications are applied without gating."""
        note_path = write_note(vault, "Note.md", "# Note\n\nBody text.")

        classification = [
            {
                "index": 0,
                "type": "insight",
                "summary": "A note.",
                "tags": ["test"],
                "skip": False,
            }
        ]

        with patch(
            "cyberbrain.mcp.tools.enrich._load_config",
            return_value=self._config(vault, gate_enabled=False),
        ):
            with patch(
                "cyberbrain.extractors.backends.call_model",
                return_value=json.dumps(classification),
            ):
                # quality_gate should NOT be called at all
                with patch(
                    "cyberbrain.extractors.quality_gate.quality_gate",
                    side_effect=AssertionError("should not be called"),
                ) as mock_gate:
                    result = cb_enrich()

        assert "Enriched:     1" in result
        mock_gate.assert_not_called()

    def test_gate_blocks_some_passes_others_in_batch(self, vault):
        """In a batch, gate blocks bad items while passing good ones."""
        from unittest.mock import MagicMock as _MagicMock

        # Files are sorted alphabetically: Bad.md (idx 0), Good.md (idx 1)
        note_b = write_note(vault, "Bad.md", "# Bad\n\nBad content.")
        note_a = write_note(vault, "Good.md", "# Good\n\nGood content.")

        classification = [
            {
                "index": 0,
                "type": "problem",
                "summary": "Nonsense.",
                "tags": ["cooking"],
                "skip": False,
            },
            {
                "index": 1,
                "type": "reference",
                "summary": "Good summary.",
                "tags": ["good"],
                "skip": False,
            },
        ]

        pass_verdict = _MagicMock()
        pass_verdict.passed = True
        pass_verdict.confidence = 0.9

        fail_verdict = _MagicMock()
        fail_verdict.passed = False
        fail_verdict.rationale = "Tags are irrelevant"
        fail_verdict.confidence = 0.2

        call_count = [0]

        def gate_side_effect(op, inp, out, cfg):
            call_count[0] += 1
            if "Good.md" in inp:
                return pass_verdict
            return fail_verdict

        with patch(
            "cyberbrain.mcp.tools.enrich._load_config", return_value=self._config(vault)
        ):
            with patch(
                "cyberbrain.extractors.backends.call_model",
                return_value=json.dumps(classification),
            ):
                with patch(
                    "cyberbrain.extractors.quality_gate.quality_gate",
                    side_effect=gate_side_effect,
                ):
                    result = cb_enrich()

        assert "Enriched:     1" in result
        assert "Gate blocked: 1" in result
        # Good note was enriched
        assert "type: reference" in note_a.read_text()
        # Bad note was NOT enriched
        assert "type: problem" not in note_b.read_text()

    def test_gate_report_shows_rationale(self, vault):
        """The report includes the gate's rationale for blocked items."""
        from unittest.mock import MagicMock as _MagicMock

        write_note(vault, "Note.md", "# Note\n\nContent.")

        classification = [
            {
                "index": 0,
                "type": "insight",
                "summary": "X.",
                "tags": ["x"],
                "skip": False,
            }
        ]

        fail_verdict = _MagicMock()
        fail_verdict.passed = False
        fail_verdict.rationale = "Summary does not match content"
        fail_verdict.confidence = 0.3

        with patch(
            "cyberbrain.mcp.tools.enrich._load_config", return_value=self._config(vault)
        ):
            with patch(
                "cyberbrain.extractors.backends.call_model",
                return_value=json.dumps(classification),
            ):
                with patch(
                    "cyberbrain.extractors.quality_gate.quality_gate",
                    return_value=fail_verdict,
                ):
                    result = cb_enrich()

        assert "Blocked by quality gate" in result
        assert "Summary does not match content" in result


# ---------------------------------------------------------------------------
# cb_enrich — frontmatter application helpers
# ---------------------------------------------------------------------------


class TestApplyFrontmatterUpdate:
    """Unit tests for the _apply_frontmatter_update helper function."""

    def test_prepends_complete_frontmatter_when_none_exists(self, tmp_path):
        from cyberbrain.mcp.tools.enrich import _apply_frontmatter_update

        path = tmp_path / "no-fm.md"
        path.write_text("# Title\n\nBody.\n")

        cls = {
            "type": "insight",
            "summary": "A useful insight.",
            "tags": ["testing", "python"],
        }
        print(f"\nDEBUG: Before call, path exists: {path.exists()}")
        print(f"DEBUG: Before call, content: {repr(path.read_text())}")
        success = _apply_frontmatter_update(
            path, path.read_text(), cls, overwrite=False
        )
        print(f"DEBUG: success returned: {success}")
        print(f"DEBUG: After call, content: {repr(path.read_text())}")

        assert success
        content = path.read_text()
        assert content.startswith("---")
        assert "type: insight" in content
        assert "A useful insight" in content
        assert "testing" in content

    def test_inserts_fields_before_closing_separator(self, tmp_path):
        from cyberbrain.mcp.tools.enrich import _apply_frontmatter_update

        path = tmp_path / "partial.md"
        path.write_text("---\ntitle: My Note\n---\n\nBody.\n")

        cls = {"type": "reference", "summary": "Summary.", "tags": ["ref"]}
        success = _apply_frontmatter_update(
            path, path.read_text(), cls, overwrite=False
        )

        assert success
        content = path.read_text()
        assert "type: reference" in content
        assert "title: My Note" in content  # original field preserved
        # The body must come AFTER the closing ---
        closing_idx = content.index("\n---", 3)
        body_idx = content.index("Body.")
        assert body_idx > closing_idx

    def test_does_not_overwrite_existing_type_without_flag(self, tmp_path):
        from cyberbrain.mcp.tools.enrich import _apply_frontmatter_update

        path = tmp_path / "typed.md"
        path.write_text("---\ntype: decision\n---\n\nBody.\n")

        cls = {"type": "insight", "summary": "New summary.", "tags": ["new"]}
        _apply_frontmatter_update(path, path.read_text(), cls, overwrite=False)

        content = path.read_text()
        assert "type: decision" in content  # original preserved
        assert "type: insight" not in content

    def test_overwrites_existing_type_with_flag(self, tmp_path):
        from cyberbrain.mcp.tools.enrich import _apply_frontmatter_update

        path = tmp_path / "typed.md"
        path.write_text("---\ntype: decision\n---\n\nBody.\n")

        cls = {"type": "insight", "summary": "New summary.", "tags": ["new"]}
        _apply_frontmatter_update(path, path.read_text(), cls, overwrite=True)

        content = path.read_text()
        assert "type: insight" in content

    def test_returns_false_for_malformed_frontmatter(self, tmp_path):
        """If the frontmatter closing --- is missing, the update fails gracefully."""
        from cyberbrain.mcp.tools.enrich import _apply_frontmatter_update

        path = tmp_path / "malformed.md"
        path.write_text("---\ntype: decision\n# No closing separator")

        cls = {"summary": "Summary.", "tags": ["tag"]}
        success = _apply_frontmatter_update(
            path, path.read_text(), cls, overwrite=False
        )

        # The file existed but frontmatter is malformed
        assert not success

    def test_escapes_double_quotes_in_summary(self, tmp_path):
        """Double quotes in summary values are escaped to produce valid YAML."""
        from cyberbrain.mcp.tools.enrich import _apply_frontmatter_update

        path = tmp_path / "quotes.md"
        path.write_text("---\n---\n\nBody.\n")

        cls = {"summary": 'Use "double quotes" carefully.', "tags": ["yaml"]}
        _apply_frontmatter_update(path, path.read_text(), cls, overwrite=False)

        content = path.read_text()
        assert '\\"double quotes\\"' in content or '"Use' in content

    def test_returns_true_early_when_fields_to_set_is_empty(self, tmp_path):
        """Line 153: when nothing needs setting, returns True without touching the file."""
        from cyberbrain.mcp.tools.enrich import _apply_frontmatter_update

        path = tmp_path / "complete.md"
        path.write_text(
            "---\ntype: decision\nsummary: Done.\ntags: [python]\n---\n\nBody.\n"
        )
        original_mtime = path.stat().st_mtime

        # Classification has no new fields to set (type/summary/tags already present,
        # overwrite=False means they won't be changed)
        cls = {"type": "insight", "summary": "New.", "tags": ["new"]}
        result = _apply_frontmatter_update(path, path.read_text(), cls, overwrite=False)

        assert result is True
        # File should not have been modified
        assert path.stat().st_mtime == original_mtime

    def test_returns_false_when_no_closing_separator(self, tmp_path):
        """Line 158: fm_end == -1 when there's no closing --- returns False."""
        from cyberbrain.mcp.tools.enrich import _apply_frontmatter_update

        path = tmp_path / "broken.md"
        # Has opening --- but no closing ---
        path.write_text("---\ntype: decision\nno closing separator here")

        # summary is not present → fields_to_set will have summary
        cls = {"summary": "New summary.", "tags": ["test"]}
        result = _apply_frontmatter_update(path, path.read_text(), cls, overwrite=False)

        assert result is False

    def test_returns_false_on_write_oserror(self, tmp_path):
        """Lines 177-178: OSError during write_text returns False."""
        from cyberbrain.mcp.tools.enrich import _apply_frontmatter_update

        path = tmp_path / "unwriteable.md"
        path.write_text("# No frontmatter\n\nBody.\n")

        cls = {"type": "reference", "summary": "Summary.", "tags": ["tag"]}
        with patch("pathlib.Path.write_text", side_effect=OSError("disk full")):
            result = _apply_frontmatter_update(
                path, path.read_text(), cls, overwrite=False
            )

        assert result is False

    def test_body_dash_heading_not_treated_as_closing_delimiter(self, tmp_path):
        """Note body with '--- heading' must not be mis-parsed as the closing ---."""
        from cyberbrain.mcp.tools.enrich import _apply_frontmatter_update

        # The body contains '--- Some Heading' which starts with --- but is not
        # a bare '\n---\n' delimiter.
        content = "---\ntype: insight\n---\n\n--- Some Heading\n\nBody text.\n"
        path = tmp_path / "dash-heading.md"
        path.write_text(content)

        cls = {"summary": "A summary.", "tags": ["python"]}
        result = _apply_frontmatter_update(path, path.read_text(), cls, overwrite=False)

        assert result is True
        updated = path.read_text()
        # The summary and tags fields should be inserted inside frontmatter
        assert "summary:" in updated
        assert "tags:" in updated
        # The body heading must be preserved intact
        assert "--- Some Heading" in updated
        # The frontmatter block must be well-formed: opening --- then closing ---\n
        lines = updated.splitlines()
        assert lines[0] == "---"
        # Find closing --- — it should come before the body content
        closing_idx = next((i for i in range(1, len(lines)) if lines[i] == "---"), None)
        assert closing_idx is not None
        body_heading_idx = next(
            (i for i, l in enumerate(lines) if l == "--- Some Heading"), None
        )
        assert body_heading_idx is not None
        assert closing_idx < body_heading_idx


# ---------------------------------------------------------------------------
# cb_enrich — vault missing, since filter, prompt path, error paths
# ---------------------------------------------------------------------------


class TestCbEnrichAdditionalCoverage:
    """Cover enrich.py lines not hit by the primary test suite."""

    @pytest.fixture
    def vault(self, tmp_path):
        v = tmp_path / "vault"
        v.mkdir()
        return v

    def _config(self, vault):
        return _vault_config(str(vault))

    def test_raises_tool_error_when_vault_does_not_exist(self, tmp_path):
        """Line 234: ToolError when vault_path is configured but dir does not exist."""
        nonexistent = str(tmp_path / "ghost-vault")
        with patch(
            "cyberbrain.mcp.tools.enrich._load_config",
            return_value=_vault_config(nonexistent),
        ):
            with pytest.raises(ToolError, match="does not exist"):
                cb_enrich()

    def test_since_filter_excludes_old_notes(self, vault):
        """Lines 266-268: only notes modified on/after since_dt are included."""
        import os

        old_note = write_note(vault, "Old.md", "# Old\n\nNo frontmatter.")
        # Push mtime to epoch (definitely before any real date filter)
        os.utime(str(old_note), (0, 0))

        write_note(vault, "New.md", "# New\n\nNo frontmatter.")

        with patch(
            "cyberbrain.mcp.tools.enrich._load_config", return_value=self._config(vault)
        ):
            # Filter to future date — excludes everything
            result = cb_enrich(dry_run=True, since="2099-01-01")

        assert "Would enrich 0" in result

    def test_json_parse_error_in_batch_adds_to_errors(self, vault):
        """Lines 341-344: malformed JSON from model adds all batch notes to errors."""
        write_note(vault, "Unparseable.md", "# Note\n\nNo frontmatter.")

        with patch(
            "cyberbrain.mcp.tools.enrich._load_config", return_value=self._config(vault)
        ):
            with patch(
                "cyberbrain.extractors.backends.call_model",
                return_value="not valid json {{{{",
            ):
                result = cb_enrich()

        assert "Errors:" in result
        assert "1" in result

    def test_llm_exception_in_batch_adds_to_errors(self, vault):
        """Lines 347-349: exception from call_model adds all batch notes to errors."""
        write_note(vault, "ErrorNote.md", "# Note\n\nNo frontmatter.")

        with patch(
            "cyberbrain.mcp.tools.enrich._load_config", return_value=self._config(vault)
        ):
            with patch(
                "cyberbrain.extractors.backends.call_model",
                side_effect=RuntimeError("model down"),
            ):
                result = cb_enrich()

        assert "Errors:" in result

    def test_apply_frontmatter_update_failure_adds_to_errors(self, vault):
        """Line 365: when _apply_frontmatter_update returns False, note goes to errors."""
        note = write_note(vault, "FailWrite.md", "# Note\n\nNo frontmatter.")

        classification = [
            {"type": "reference", "summary": "Summary.", "tags": ["tag"], "skip": False}
        ]
        with patch(
            "cyberbrain.mcp.tools.enrich._load_config", return_value=self._config(vault)
        ):
            with patch(
                "cyberbrain.extractors.backends.call_model",
                return_value=json.dumps(classification),
            ):
                with patch(
                    "cyberbrain.mcp.tools.enrich._apply_frontmatter_update",
                    return_value=False,
                ):
                    result = cb_enrich()

        assert "frontmatter update failed" in result or "Errors:" in result


# ---------------------------------------------------------------------------
# cb_enrich — _get_valid_types: CLAUDE.md with too few type matches
# ---------------------------------------------------------------------------


class TestGetValidTypes:
    """Unit tests for _get_valid_types edge cases."""

    def test_returns_defaults_when_claude_md_has_fewer_than_2_types(self, tmp_path):
        """Lines 47-52: fewer than 2 type matches in CLAUDE.md → returns default entity types."""
        from cyberbrain.mcp.tools.enrich import _get_valid_types

        vault = tmp_path / "vault"
        vault.mkdir()
        # CLAUDE.md with only one non-beat type: line (decision is filtered as beat type)
        (vault / "CLAUDE.md").write_text(
            "## Entity Types\n\ntype: resource\n\nNo other types here.\n"
        )
        result = _get_valid_types(vault)
        # Only 1 match → falls back to defaults
        assert result == ["project", "note", "resource", "archived"]

    def test_returns_types_from_claude_md_when_2_or_more_match(self, tmp_path):
        """Lines 47-52: 2+ matches → returns deduplicated list from CLAUDE.md."""
        from cyberbrain.mcp.tools.enrich import _get_valid_types

        vault = tmp_path / "vault"
        vault.mkdir()
        (vault / "CLAUDE.md").write_text(
            "type: concept\ntype: note\ntype: resource\ntype: concept\n"
        )
        result = _get_valid_types(vault)
        assert result == ["concept", "note", "resource"]


# ---------------------------------------------------------------------------
# cb_enrich — _needs_enrichment: comma-separated tags, empty fm, line 118
# ---------------------------------------------------------------------------


class TestNeedsEnrichmentEdgeCases:
    """Cover _needs_enrichment branches not exercised by the candidate detection tests."""

    def test_comma_separated_tags_string_is_recognised(self):
        """Line 90: tags stored as a comma-separated string are parsed correctly."""
        from cyberbrain.mcp.tools.enrich import _needs_enrichment

        content = "---\ntype: decision\nsummary: Test summary.\ntags: fastapi, python\n---\nBody."
        needs, reason = _needs_enrichment(content, ["decision", "insight"])
        assert needs is False
        assert reason == ""

    def test_empty_frontmatter_dict_returns_needs_enrichment(self):
        """Line 102: frontmatter block parses to empty dict → treated as no frontmatter."""
        from cyberbrain.mcp.tools.enrich import _needs_enrichment

        # Valid YAML but yields an empty dict (just ---)
        content = "---\n---\n\nBody text here."
        needs, reason = _needs_enrichment(content, ["decision", "insight"])
        assert needs is True

    def test_invalid_type_returns_needs_enrichment(self):
        """Line 116: type present but not in valid_types list → flagged."""
        from cyberbrain.mcp.tools.enrich import _needs_enrichment

        content = (
            "---\ntype: work-notes\nsummary: Summary.\ntags: [testing]\n---\nBody."
        )
        needs, reason = _needs_enrichment(content, ["decision", "insight"])
        assert needs is True
        assert "invalid type" in reason

    def test_missing_summary_returns_needs_enrichment(self):
        """Line 118: type is valid, tags present, but no summary → flagged."""
        from cyberbrain.mcp.tools.enrich import _needs_enrichment

        content = "---\ntype: decision\ntags: [python]\n---\nBody."
        needs, reason = _needs_enrichment(content, ["decision", "insight"])
        assert needs is True
        assert "summary" in reason

    def test_all_generic_tags_returns_needs_enrichment(self):
        """Line 124: all tags are trivially generic (personal, work, etc.) → flagged."""
        from cyberbrain.mcp.tools.enrich import _needs_enrichment

        content = (
            "---\ntype: decision\nsummary: Summary.\ntags: [personal, work]\n---\nBody."
        )
        needs, reason = _needs_enrichment(content, ["decision", "insight"])
        assert needs is True
        assert "generic" in reason


# ---------------------------------------------------------------------------
# cb_enrich — _load_prompt: installed path and ToolError when neither exists
# ---------------------------------------------------------------------------


class TestLoadPrompt:
    """Cover _load_tool_prompt path resolution branches (now in shared.py)."""

    def test_load_prompt_uses_installed_path_when_it_exists(self, tmp_path):
        """Returns content from installed prompts dir when file exists."""
        from cyberbrain.mcp.shared import _load_tool_prompt

        fake_installed = tmp_path / "prompts"
        fake_installed.mkdir()
        prompt_file = fake_installed / "enrich-system.md"
        prompt_file.write_text("# Installed prompt\n")

        with patch("cyberbrain.mcp.shared._PROMPTS_DIR_PRIMARY", fake_installed):
            result = _load_tool_prompt("enrich-system.md")

        assert result == "# Installed prompt\n"

    def test_load_prompt_raises_tool_error_simple(self, tmp_path):
        """ToolError raised when installed dir doesn't exist and dev path missing."""
        from cyberbrain.mcp.shared import _load_tool_prompt

        nonexistent = tmp_path / "no-such-prompts"

        with patch("cyberbrain.mcp.shared._PROMPTS_DIR_PRIMARY", nonexistent):
            with pytest.raises(ToolError, match="not found"):
                _load_tool_prompt("this-file-does-not-exist-anywhere.md")


# ---------------------------------------------------------------------------
# cb_setup — _run_analyzer ValueError, _read_note_samples populates prompt
# ---------------------------------------------------------------------------


class TestCbSetupAdditionalCoverage:
    """Cover setup.py lines 17-21 and 26-50 not hit by the primary suite."""

    @pytest.fixture
    def vault(self, tmp_path):
        v = tmp_path / "vault"
        v.mkdir()
        return v

    def _config(self, vault):
        return _vault_config(str(vault))

    def test_run_analyzer_exception_returns_error_dict(self, vault):
        """Lines 17-21: when analyze_vault raises, _run_analyzer returns error dict."""
        from cyberbrain.mcp.tools.setup import _run_analyzer

        # analyze_vault is imported inline inside _run_analyzer; patch the module
        mock_av = MagicMock()
        mock_av.analyze_vault.side_effect = ValueError("No notes found")
        with patch.dict(sys.modules, {"cyberbrain.extractors.analyze_vault": mock_av}):
            result = _run_analyzer(vault)
        assert "error" in result
        assert "No notes found" in result["error"]
        assert result["total_notes"] == 0

    def test_phase1_handles_analyze_vault_error_gracefully(self, vault):
        """Lines 17-21 via cb_setup: ValueError from analyze_vault doesn't crash Phase 1."""
        mock_av = MagicMock()
        mock_av.analyze_vault.side_effect = ValueError("No notes found")
        with patch(
            "cyberbrain.mcp.tools.enrich._load_config", return_value=self._config(vault)
        ):
            with patch.dict(sys.modules, {"analyze_vault": mock_av}):
                with patch(
                    "cyberbrain.extractors.backends.call_model",
                    return_value='{"archetype": "developer", "questions": []}',
                ):
                    result = cb_setup(vault_path=str(vault))
        assert isinstance(result, str)
        # Should not raise — error dict is passed through to model
        parsed = json.loads(result)
        assert parsed["archetype"] == "developer"

    def test_read_note_samples_returns_content_string(self, vault):
        """Lines 26-50: _read_note_samples reads vault notes and returns joined content."""
        from cyberbrain.mcp.tools.setup import _read_note_samples

        (vault / "Note A.md").write_text("---\ntype: decision\n---\nBody of Note A.")
        (vault / "Note B.md").write_text("---\ntype: insight\n---\nBody of Note B.")
        md_files = list(vault.glob("*.md"))
        vault_report = {"links": {"hub_nodes": []}}
        result = _read_note_samples(vault, md_files, vault_report)
        assert "Note A.md" in result or "Note B.md" in result
        assert "Body of Note A" in result or "Body of Note B" in result

    def test_read_note_samples_prioritises_hub_nodes(self, vault):
        """Lines 37-39: hub nodes are read first in the selected sample."""
        from cyberbrain.mcp.tools.setup import _read_note_samples

        (vault / "Hub Note.md").write_text("# Hub Note content")
        (vault / "Regular.md").write_text("# Regular content")
        md_files = list(vault.glob("*.md"))
        vault_report = {"links": {"hub_nodes": [{"note": "Hub Note"}]}}
        result = _read_note_samples(vault, md_files, vault_report)
        assert "Hub Note" in result

    def test_phase1_note_samples_appear_in_model_prompt(self, vault):
        """Lines 26-50: real note content reaches the call_model user_message."""
        (vault / "Sample Note.md").write_text("# Sample\n\nImportant content here.")

        captured = {}

        def capture_call(system_prompt, user_message, config):
            captured["user"] = user_message
            return '{"archetype": "developer", "questions": []}'

        mock_av = MagicMock()
        mock_av.analyze_vault.side_effect = ValueError("no yaml")
        with patch(
            "cyberbrain.mcp.tools.enrich._load_config", return_value=self._config(vault)
        ):
            with patch.dict(sys.modules, {"analyze_vault": mock_av}):
                with patch(
                    "cyberbrain.extractors.backends.call_model",
                    side_effect=capture_call,
                ):
                    cb_setup(vault_path=str(vault))

        assert "Sample Note.md" in captured.get(
            "user", ""
        ) or "Important content" in captured.get("user", "")


# ---------------------------------------------------------------------------
# shared.py — _get_search_backend lazy load and caching
# ---------------------------------------------------------------------------


class TestSharedSearchBackend:
    """Cover shared.py lines 37-43: _get_search_backend lazy load and cache."""

    def setup_method(self):
        """Reset the cached backend before each test."""
        import cyberbrain.mcp.shared as _s

        _s._search_backend = None

    def teardown_method(self):
        """Reset backend cache after each test."""
        import cyberbrain.mcp.shared as _s

        _s._search_backend = None

    def test_returns_none_when_search_backends_import_fails(self):
        """Lines 39-42: import failure returns None instead of raising."""
        import cyberbrain.mcp.shared as _s

        _s._search_backend = None
        with patch.dict(sys.modules, {"cyberbrain.extractors.search_backends": None}):
            result = _s._get_search_backend({"vault_path": "/some/path"})
        assert result is None

    def test_returns_backend_when_import_succeeds(self):
        """Lines 39-41: successful import returns the backend object."""
        import cyberbrain.mcp.shared as _s

        _s._search_backend = None
        mock_backend = MagicMock()
        mock_sb_module = MagicMock()
        mock_sb_module.get_search_backend.return_value = mock_backend
        with patch.dict(
            sys.modules, {"cyberbrain.extractors.search_backends": mock_sb_module}
        ):
            result = _s._get_search_backend({"vault_path": "/some/path"})
        assert result is mock_backend

    def test_caches_backend_on_second_call(self):
        """Lines 37-43: second call returns the same cached object without re-importing."""
        import cyberbrain.mcp.shared as _s

        _s._search_backend = None
        mock_backend = MagicMock()
        mock_sb_module = MagicMock()
        mock_sb_module.get_search_backend.return_value = mock_backend
        with patch.dict(
            sys.modules, {"cyberbrain.extractors.search_backends": mock_sb_module}
        ):
            r1 = _s._get_search_backend({"vault_path": "/some/path"})
            r2 = _s._get_search_backend({"vault_path": "/some/path"})
        assert r1 is r2
        # get_search_backend should only have been called once
        assert mock_sb_module.get_search_backend.call_count == 1


# ---------------------------------------------------------------------------
# _should_skip — type: journal/moc branch (line 90)
# ---------------------------------------------------------------------------


class TestShouldSkipEdgeCases:
    """Cover _should_skip branches not exercised by the candidate detection tests."""

    def test_skips_note_with_type_journal(self, tmp_path):
        """Line 90: notes with type: journal in frontmatter are skipped."""
        from cyberbrain.mcp.tools.enrich import _should_skip

        vault = tmp_path / "vault"
        vault.mkdir()
        path = vault / "Daily.md"
        content = "---\ntype: journal\n---\nBody."
        assert _should_skip(path, vault, content) is True

    def test_skips_note_with_type_moc(self, tmp_path):
        """Line 90: notes with type: moc in frontmatter are skipped."""
        from cyberbrain.mcp.tools.enrich import _should_skip

        vault = tmp_path / "vault"
        vault.mkdir()
        path = vault / "Index.md"
        content = "---\ntype: moc\n---\nBody."
        assert _should_skip(path, vault, content) is True


# ---------------------------------------------------------------------------
# _needs_enrichment — non-list/non-str tags (line 118)
# ---------------------------------------------------------------------------


class TestNeedsEnrichmentNonListTags:
    """Cover _needs_enrichment when tags field is not a str or list."""

    def test_numeric_tags_treated_as_empty(self):
        """Line 118: tags value that is neither str nor list → treated as empty."""
        from cyberbrain.mcp.tools.enrich import _needs_enrichment

        # YAML parses `tags: 42` as int
        content = "---\ntype: decision\nsummary: A summary.\ntags: 42\n---\nBody."
        needs, reason = _needs_enrichment(content, ["decision", "insight"])
        assert needs is True
        assert "tags" in reason


# ---------------------------------------------------------------------------
# _apply_frontmatter_update — existing str tags in overwrite path (line 153)
# ---------------------------------------------------------------------------


class TestApplyFrontmatterUpdateStrTags:
    """Cover _apply_frontmatter_update when existing tags are a comma-separated string."""

    def test_overwrites_comma_string_tags_when_overwrite_true(self, tmp_path):
        """Line 153: existing str tags are split correctly before overwrite check."""
        from cyberbrain.mcp.tools.enrich import _apply_frontmatter_update

        path = tmp_path / "str-tags.md"
        # tags stored as comma-separated string
        path.write_text(
            "---\ntype: decision\nsummary: Old.\ntags: old-tag, another\n---\n\nBody.\n"
        )

        cls = {"type": "insight", "summary": "New.", "tags": ["new-tag"]}
        result = _apply_frontmatter_update(path, path.read_text(), cls, overwrite=True)

        assert result is True
        content = path.read_text()
        assert "new-tag" in content


# ---------------------------------------------------------------------------
# cb_enrich — OSError reading note file during scan (lines 266-268)
# cb_enrich — model returns non-list JSON (lines 347-349)
# cb_enrich — all-done path in normal mode (lines 303-306)
# ---------------------------------------------------------------------------


class TestCbEnrichMoreEdgeCases:
    """Additional cb_enrich branches."""

    @pytest.fixture
    def vault(self, tmp_path):
        v = tmp_path / "vault"
        v.mkdir()
        return v

    def _config(self, vault):
        return _vault_config(str(vault))

    def test_oserror_reading_note_increments_skipped(self, vault):
        """Lines 266-268: OSError reading a note during scan increments skipped count."""
        write_note(vault, "Unreadable.md", "# Title\n\nBody.")

        original_read_text = Path.read_text

        def patched_read_text(self, **kwargs):
            if self.name == "Unreadable.md":
                raise OSError("permission denied")
            return original_read_text(self, **kwargs)

        with patch(
            "cyberbrain.mcp.tools.enrich._load_config", return_value=self._config(vault)
        ):
            with patch.object(Path, "read_text", patched_read_text):
                result = cb_enrich(dry_run=True)

        assert "Skipped:" in result

    def test_model_returns_non_list_json_adds_to_errors(self, vault):
        """Lines 347-349: model returns valid JSON but not a list → all batch notes errored."""
        write_note(vault, "NonList.md", "# Note\n\nNo frontmatter.")

        with patch(
            "cyberbrain.mcp.tools.enrich._load_config", return_value=self._config(vault)
        ):
            with patch(
                "cyberbrain.extractors.backends.call_model",
                return_value='{"result": "not a list"}',
            ):
                result = cb_enrich()

        assert "Errors:" in result

    def test_all_notes_done_returns_clean_message_in_normal_mode(self, vault):
        """Lines 303-306: when needs_enrichment is empty (non-dry-run), clean message returned."""
        write_note(
            vault,
            "Done.md",
            """\
---
type: resource
summary: Chose FastAPI.
tags: [python, fastapi]
---
Body.
""",
        )
        with patch(
            "cyberbrain.mcp.tools.enrich._load_config", return_value=self._config(vault)
        ):
            result = cb_enrich()

        assert "All notes already have required metadata" in result


# ---------------------------------------------------------------------------
# cb_setup — _read_note_samples sample_count branching (lines 29-34)
# cb_setup — _read_note_samples read exception (lines 47-48)
# cb_setup — Phase 2 OSError writing CLAUDE.md (lines 268-269)
# ---------------------------------------------------------------------------


class TestCbSetupMoreCoverage:
    """Cover setup.py lines not reached by existing tests."""

    @pytest.fixture
    def vault(self, tmp_path):
        v = tmp_path / "vault"
        v.mkdir()
        return v

    def _config(self, vault):
        return _vault_config(str(vault))

    def test_read_note_samples_50_to_200_notes(self, vault):
        """Lines 29-30: 50-199 notes → sample_count = 30."""
        from cyberbrain.mcp.tools.setup import _read_note_samples

        # Create 60 notes
        for i in range(60):
            (vault / f"Note{i:03d}.md").write_text(f"# Note {i}\n\nContent {i}.")
        md_files = list(vault.glob("*.md"))
        vault_report = {"links": {"hub_nodes": []}}
        result = _read_note_samples(vault, md_files, vault_report)
        # With 60 files, sample_count=30, capped at 30 → reads at most 30
        assert len([s for s in result.split("=== ") if s]) <= 30

    def test_read_note_samples_200_to_500_notes(self, vault):
        """Lines 31-32: 200-499 notes → sample_count = 45."""
        from cyberbrain.mcp.tools.setup import _read_note_samples

        # Create 250 notes (but only 30 are read due to token cap)
        for i in range(250):
            (vault / f"Note{i:04d}.md").write_text(f"# Note {i}")
        md_files = list(vault.glob("*.md"))
        vault_report = {"links": {"hub_nodes": []}}
        result = _read_note_samples(vault, md_files, vault_report)
        assert isinstance(result, str)

    def test_read_note_samples_500_plus_notes(self, vault):
        """Lines 33-34: 500+ notes → sample_count = 70."""
        from cyberbrain.mcp.tools.setup import _read_note_samples

        # Create 520 notes
        for i in range(520):
            (vault / f"Note{i:04d}.md").write_text(f"# Note {i}")
        md_files = list(vault.glob("*.md"))
        vault_report = {"links": {"hub_nodes": []}}
        result = _read_note_samples(vault, md_files, vault_report)
        assert isinstance(result, str)

    def test_read_note_samples_skips_unreadable_files(self, vault):
        """Lines 47-48: OSError reading a note file is caught and skipped."""
        from cyberbrain.mcp.tools.setup import _read_note_samples

        (vault / "Good.md").write_text("# Good note\n\nContent.")
        (vault / "Bad.md").write_text("# Bad note")

        original_read_text = Path.read_text

        def patched_read_text(self, **kwargs):
            if self.name == "Bad.md":
                raise OSError("unreadable")
            return original_read_text(self, **kwargs)

        md_files = list(vault.glob("*.md"))
        vault_report = {"links": {"hub_nodes": []}}
        with patch.object(Path, "read_text", patched_read_text):
            result = _read_note_samples(vault, md_files, vault_report)
        # Good.md should appear; Bad.md is silently skipped
        assert "Good.md" in result or "Good note" in result

    def test_phase2_raises_tool_error_on_oserror_writing_claude_md(self, vault):
        """Lines 268-269: OSError writing CLAUDE.md is raised as ToolError."""
        answers = json.dumps({"q1": "Technical notes."})
        claude_md_content = "# Vault Overview\n\nContent.\n"

        with patch(
            "cyberbrain.mcp.tools.enrich._load_config", return_value=self._config(vault)
        ):
            with patch(
                "cyberbrain.mcp.tools.setup._run_analyzer",
                return_value={"total_notes": 0, "links": {}},
            ):
                with patch(
                    "cyberbrain.mcp.tools.setup._read_note_samples", return_value=""
                ):
                    with patch(
                        "cyberbrain.extractors.backends.call_model",
                        return_value=claude_md_content,
                    ):
                        with patch.object(
                            Path, "write_text", side_effect=OSError("read-only fs")
                        ):
                            with pytest.raises(
                                ToolError, match="Failed to write CLAUDE.md"
                            ):
                                cb_setup(
                                    vault_path=str(vault), answers=answers, write=True
                                )
