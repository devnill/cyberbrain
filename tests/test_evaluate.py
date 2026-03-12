"""
test_evaluate.py — tests for the evaluation tooling framework.

Tests cover:
- Variant and EvalResult dataclass construction
- Config override merging
- Diff computation
- Evaluation pipeline with mocked LLM calls
- Result persistence (JSON + markdown)
- LLM-as-judge scoring
- Error handling for failed variants
- CLI argument parsing
"""

import json
import sys
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# sys.path setup
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent
EXTRACTORS_DIR = REPO_ROOT / "src" / "cyberbrain" / "extractors"


# ---------------------------------------------------------------------------
# Mock extract_beats before importing evaluate (it pulls from backends/config)
# ---------------------------------------------------------------------------

class _BackendError(Exception):
    pass


_mock_eb = MagicMock()
_mock_eb.BackendError = _BackendError
_mock_eb.resolve_config.return_value = {
    "vault_path": "/tmp/test_vault",
    "inbox": "AI/Claude-Sessions",
    "backend": "claude-code",
    "model": "claude-haiku-4-5",
}

if "cyberbrain.extractors.extract_beats" not in sys.modules:
    sys.modules["cyberbrain.extractors.extract_beats"] = _mock_eb
if "cyberbrain.extractors.frontmatter" not in sys.modules:
    sys.modules["cyberbrain.extractors.frontmatter"] = MagicMock()

# Mock backends.call_model and config.load_prompt before evaluate imports them.
# Save originals so we can restore after import to avoid contaminating other tests.
_orig_backends = sys.modules.get("cyberbrain.extractors.backends")
_orig_config = sys.modules.get("cyberbrain.extractors.config")

_mock_backends = MagicMock()
_mock_backends.call_model = MagicMock(return_value="{}")
_mock_backends.BackendError = _BackendError
sys.modules["cyberbrain.extractors.backends"] = _mock_backends

_mock_config = MagicMock()
_mock_config.load_prompt = MagicMock(return_value="prompt template")
_mock_config.resolve_config = MagicMock(return_value={"model": "test"})
_mock_config.GLOBAL_CONFIG_PATH = EXTRACTORS_DIR / "config.json"
_mock_config.load_global_config = MagicMock(return_value={})
_mock_config.find_project_config = MagicMock(return_value={})
_mock_config.PROMPTS_DIR = REPO_ROOT / "prompts"
sys.modules["cyberbrain.extractors.config"] = _mock_config

# Clear any cached evaluate module
sys.modules.pop("cyberbrain.extractors.evaluate", None)

# Now import the module under test
from cyberbrain.extractors.evaluate import (
    Variant,
    VariantOutput,
    Score,
    EvalResult,
    _build_config_with_overrides,
    _compute_diff,
    evaluate,
    save_result,
    format_summary,
)

# Restore original modules so other test files get the real ones
for _name, _orig in [("cyberbrain.extractors.backends", _orig_backends), ("cyberbrain.extractors.config", _orig_config)]:
    if _orig is not None:
        sys.modules[_name] = _orig
    else:
        sys.modules.pop(_name, None)


# ---------------------------------------------------------------------------
# Tests: Dataclasses
# ---------------------------------------------------------------------------


class TestVariant:
    def test_basic_construction(self):
        v = Variant(name="haiku", overrides={"model": "claude-haiku-4-5"})
        assert v.name == "haiku"
        assert v.overrides["model"] == "claude-haiku-4-5"

    def test_default_overrides(self):
        v = Variant(name="default")
        assert v.overrides == {}

    def test_with_params(self):
        v = Variant(name="custom", overrides={
            "model": "claude-sonnet-4-5",
            "params": {"threshold": 0.3}
        })
        assert v.overrides["params"]["threshold"] == 0.3


class TestVariantOutput:
    def test_success_output(self):
        v = Variant(name="test")
        vo = VariantOutput(variant=v, raw_output="result", duration_ms=100)
        assert vo.raw_output == "result"
        assert vo.error is None

    def test_error_output(self):
        v = Variant(name="test")
        vo = VariantOutput(variant=v, error="backend failed", duration_ms=50)
        assert vo.raw_output == ""
        assert vo.error == "backend failed"


# ---------------------------------------------------------------------------
# Tests: Config merging
# ---------------------------------------------------------------------------


class TestConfigMerging:
    def test_override_model(self):
        base = {"model": "claude-haiku-4-5", "backend": "claude-code"}
        merged = _build_config_with_overrides(base, {"model": "claude-sonnet-4-5"})
        assert merged["model"] == "claude-sonnet-4-5"
        assert merged["backend"] == "claude-code"
        # Original unchanged
        assert base["model"] == "claude-haiku-4-5"

    def test_params_not_merged_into_config(self):
        base = {"model": "claude-haiku-4-5"}
        merged = _build_config_with_overrides(base, {"params": {"threshold": 0.5}})
        assert "params" not in merged

    def test_empty_overrides(self):
        base = {"model": "claude-haiku-4-5", "backend": "claude-code"}
        merged = _build_config_with_overrides(base, {})
        assert merged == base


# ---------------------------------------------------------------------------
# Tests: Diff computation
# ---------------------------------------------------------------------------


class TestDiffComputation:
    def test_identical_texts(self):
        diff = _compute_diff("hello\nworld", "hello\nworld", "a", "b")
        assert diff == ""

    def test_different_texts(self):
        diff = _compute_diff("line1\nline2", "line1\nline3", "a", "b")
        assert "line2" in diff
        assert "line3" in diff
        assert "---" in diff or "+++" in diff

    def test_empty_inputs(self):
        diff = _compute_diff("", "", "a", "b")
        assert diff == ""


# ---------------------------------------------------------------------------
# Tests: Evaluation pipeline
# ---------------------------------------------------------------------------


class TestEvaluate:
    @patch("evaluate.call_model")
    @patch("evaluate.load_prompt")
    def test_enrich_two_variants(self, mock_load_prompt, mock_call_model):
        mock_load_prompt.return_value = "prompt {vault_type_context} {count} {notes_block}"
        mock_call_model.side_effect = [
            '[{"type": "insight", "tags": ["python"]}]',
            '[{"type": "decision", "tags": ["architecture"]}]',
        ]

        notes = [("test.md", "---\ntitle: Test\n---\nSome content")]
        variants = [
            Variant(name="haiku", overrides={"model": "claude-haiku-4-5"}),
            Variant(name="sonnet", overrides={"model": "claude-sonnet-4-5"}),
        ]
        base_config = {"model": "claude-haiku-4-5", "backend": "claude-code"}

        result = evaluate("enrich", notes, variants, base_config)

        assert result.operation == "enrich"
        assert len(result.outputs) == 2
        assert result.outputs[0]["variant"]["name"] == "haiku"
        assert result.outputs[1]["variant"]["name"] == "sonnet"
        assert result.outputs[0]["error"] is None
        assert result.outputs[1]["error"] is None
        assert len(result.diffs) == 1  # one pairwise diff
        assert result.scores == []  # no judge

    @patch("evaluate.call_model")
    @patch("evaluate.load_prompt")
    def test_variant_error_captured(self, mock_load_prompt, mock_call_model):
        mock_load_prompt.return_value = "prompt {vault_type_context} {count} {notes_block}"
        mock_call_model.side_effect = [
            Exception("API timeout"),
            '[{"type": "insight"}]',
        ]

        notes = [("test.md", "content")]
        variants = [
            Variant(name="failing", overrides={}),
            Variant(name="working", overrides={}),
        ]

        result = evaluate("enrich", notes, variants, {"model": "test"})

        assert result.outputs[0]["error"] == "API timeout"
        assert result.outputs[1]["error"] is None
        # No diff computed when one variant errored
        assert len(result.diffs) == 0

    @patch("evaluate.call_model")
    @patch("evaluate.load_prompt")
    def test_judge_scoring(self, mock_load_prompt, mock_call_model):
        # First two calls: variant operations; third call: judge
        mock_load_prompt.return_value = "prompt {vault_type_context} {count} {notes_block}"
        mock_call_model.side_effect = [
            '{"result": "a"}',
            '{"result": "b"}',
            '[{"variant_index": 0, "overall": 3}, {"variant_index": 1, "overall": 4}]',
        ]

        notes = [("test.md", "content")]
        variants = [
            Variant(name="v0", overrides={}),
            Variant(name="v1", overrides={}),
        ]

        result = evaluate("enrich", notes, variants, {"model": "test"}, judge=True)

        assert len(result.scores) == 2
        assert result.scores[0]["overall"] == 3
        assert result.scores[1]["overall"] == 4


# ---------------------------------------------------------------------------
# Tests: Result persistence
# ---------------------------------------------------------------------------


class TestSaveResult:
    def test_save_creates_files(self, tmp_path):
        result = EvalResult(
            operation="enrich",
            timestamp="2026-03-09T12:00:00Z",
            input_notes=[{"path": "test.md", "content": "hello"}],
            outputs=[{
                "variant": {"name": "v0", "overrides": {}},
                "raw_output": "result text",
                "duration_ms": 100,
                "error": None,
            }],
        )

        json_path, md_path = save_result(result, str(tmp_path))

        assert Path(json_path).exists()
        assert Path(md_path).exists()
        assert json_path.endswith(".json")
        assert md_path.endswith(".md")

        # Verify JSON is valid
        data = json.loads(Path(json_path).read_text())
        assert data["operation"] == "enrich"
        assert len(data["outputs"]) == 1

        # Verify markdown contains key info
        md = Path(md_path).read_text()
        assert "enrich" in md
        assert "v0" in md

    def test_save_with_scores(self, tmp_path):
        result = EvalResult(
            operation="restructure",
            timestamp="2026-03-09T12:00:00Z",
            input_notes=[],
            outputs=[],
            scores=[{"variant_index": 0, "overall": 4, "notes": "good"}],
        )

        json_path, md_path = save_result(result, str(tmp_path))
        md = Path(md_path).read_text()
        assert "Scores" in md
        assert "overall=4" in md


# ---------------------------------------------------------------------------
# Tests: Format summary
# ---------------------------------------------------------------------------


class TestFormatSummary:
    def test_basic_summary(self):
        result = EvalResult(
            operation="enrich",
            timestamp="2026-03-09T12:00:00Z",
            outputs=[
                {
                    "variant": {"name": "haiku"},
                    "raw_output": "some output",
                    "duration_ms": 150,
                    "error": None,
                },
                {
                    "variant": {"name": "sonnet"},
                    "raw_output": "",
                    "duration_ms": 50,
                    "error": "timeout",
                },
            ],
        )

        summary = format_summary(result)
        assert "haiku" in summary
        assert "OK" in summary
        assert "sonnet" in summary
        assert "ERROR" in summary

    def test_summary_with_scores(self):
        result = EvalResult(
            operation="enrich",
            timestamp="2026-03-09T12:00:00Z",
            outputs=[{
                "variant": {"name": "v0"},
                "raw_output": "x",
                "duration_ms": 100,
                "error": None,
            }],
            scores=[{"variant_index": 0, "overall": 5}],
        )

        summary = format_summary(result)
        assert "overall=5" in summary
