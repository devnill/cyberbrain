"""Tests for extractors/quality_gate.py — LLM-as-judge quality gate."""

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from cyberbrain.extractors.quality_gate import GateVerdict, Verdict, _parse_verdict
from cyberbrain.extractors.backends import BackendError

# Import the module itself for patching references
import cyberbrain.extractors.quality_gate as _qg_module


class TestGateVerdict:
    def test_basic_construction(self):
        v = GateVerdict(verdict=Verdict.PASS, passed=True, confidence=0.95, rationale="Looks good", issues=[])
        assert v.verdict == Verdict.PASS
        assert v.passed is True
        assert v.confidence == 0.95
        assert v.rationale == "Looks good"
        assert v.suggest_retry is False
        assert v.suggested_model == ""
        assert v.issues == []

    def test_with_retry(self):
        v = GateVerdict(
            verdict=Verdict.FAIL, passed=False, confidence=0.3,
            rationale="Bad merge", issues=["unrelated topics"],
            suggest_retry=True, suggested_model="claude-sonnet-4-5-20250514"
        )
        assert v.verdict == Verdict.FAIL
        assert v.passed is False
        assert v.suggest_retry is True
        assert v.issues == ["unrelated topics"]

    def test_uncertain_verdict(self):
        v = GateVerdict(
            verdict=Verdict.UNCERTAIN, passed=False, confidence=0.55,
            rationale="Ambiguous", issues=[], suggest_retry=True
        )
        assert v.verdict == Verdict.UNCERTAIN
        assert v.passed is False


class TestVerdict:
    def test_enum_values(self):
        assert Verdict.PASS == "pass"
        assert Verdict.FAIL == "fail"
        assert Verdict.UNCERTAIN == "uncertain"


class TestParseVerdict:
    def test_high_confidence_pass(self):
        raw = json.dumps({
            "passed": True, "confidence": 0.92,
            "rationale": "Merge is thematically coherent",
            "issues": []
        })
        v = _parse_verdict(raw, {"model": "claude-haiku-4-5"})
        assert v.verdict == Verdict.PASS
        assert v.passed is True
        assert v.confidence == 0.92
        assert v.suggest_retry is False

    def test_fail_verdict_suggests_model_upgrade(self):
        raw = json.dumps({
            "passed": False, "confidence": 0.3,
            "rationale": "Notes are unrelated",
            "suggest_retry": True, "issues": ["no thematic link"]
        })
        v = _parse_verdict(raw, {"model": "claude-haiku-4-5"})
        assert v.verdict == Verdict.FAIL
        assert v.passed is False
        assert v.suggest_retry is True
        assert v.suggested_model == "claude-sonnet-4-5-20250514"
        assert v.issues == ["no thematic link"]

    def test_fail_no_upgrade_for_strong_model(self):
        raw = json.dumps({
            "passed": False, "confidence": 0.4,
            "rationale": "Poor quality", "issues": []
        })
        v = _parse_verdict(raw, {"model": "claude-sonnet-4-5-20250514"})
        assert v.verdict == Verdict.FAIL
        assert v.suggested_model == ""

    def test_low_confidence_pass_is_uncertain(self):
        raw = json.dumps({
            "passed": True, "confidence": 0.55,
            "rationale": "Ambiguous grouping", "issues": []
        })
        v = _parse_verdict(raw, {"model": "claude-haiku-4-5"})
        assert v.verdict == Verdict.UNCERTAIN
        assert v.passed is False  # uncertain is not passed
        assert v.suggest_retry is True

    def test_borderline_confidence_pass(self):
        """Confidence exactly at 0.7 threshold should pass."""
        raw = json.dumps({
            "passed": True, "confidence": 0.7,
            "rationale": "Acceptable", "issues": []
        })
        v = _parse_verdict(raw, {})
        assert v.verdict == Verdict.PASS
        assert v.passed is True

    def test_confidence_clamped(self):
        raw = json.dumps({"passed": True, "confidence": 1.5, "rationale": "ok", "issues": []})
        v = _parse_verdict(raw, {})
        assert v.confidence == 1.0

        raw = json.dumps({"passed": True, "confidence": -0.5, "rationale": "ok", "issues": []})
        v = _parse_verdict(raw, {})
        assert v.confidence == 0.0

    def test_markdown_code_fences_stripped(self):
        raw = "```json\n" + json.dumps({
            "passed": True, "confidence": 0.85, "rationale": "Good", "issues": []
        }) + "\n```"
        v = _parse_verdict(raw, {})
        assert v.verdict == Verdict.PASS
        assert v.confidence == 0.85

    def test_invalid_json_returns_uncertain(self):
        v = _parse_verdict("not json at all", {})
        assert v.verdict == Verdict.UNCERTAIN
        assert v.passed is False
        assert v.confidence == 0.0
        assert v.suggest_retry is True

    def test_missing_fields_use_defaults(self):
        raw = json.dumps({})
        v = _parse_verdict(raw, {})
        assert v.verdict == Verdict.FAIL
        assert v.passed is False
        assert v.rationale == "No rationale provided"
        assert v.issues == []

    def test_issues_preserved(self):
        raw = json.dumps({
            "passed": False, "confidence": 0.3,
            "rationale": "Bad", "issues": ["issue 1", "issue 2"]
        })
        v = _parse_verdict(raw, {})
        assert v.issues == ["issue 1", "issue 2"]


class TestQualityGate:
    @patch.object(_qg_module, "call_model")
    @patch.object(_qg_module, "load_prompt")
    def test_pass_verdict(self, mock_prompt, mock_model):
        mock_prompt.return_value = "Judge prompt for {operation}"
        mock_model.return_value = json.dumps({
            "passed": True, "confidence": 0.9,
            "rationale": "Well-formed merge", "issues": []
        })

        config = {"model": "claude-haiku-4-5"}
        v = _qg_module.quality_gate("restructure_merge", "input context", "merged output", config)

        assert v.verdict == Verdict.PASS
        assert v.passed is True
        assert v.confidence == 0.9
        mock_prompt.assert_called_once_with("quality-gate-system.md")
        call_args = mock_model.call_args
        assert "restructure_merge" in call_args[0][0]

    @patch.object(_qg_module, "call_model")
    @patch.object(_qg_module, "load_prompt")
    def test_fail_verdict(self, mock_prompt, mock_model):
        mock_prompt.return_value = "Judge prompt for {operation}"
        mock_model.return_value = json.dumps({
            "passed": False, "confidence": 0.2,
            "rationale": "Unrelated notes merged",
            "issues": ["topics diverge"]
        })

        config = {"model": "claude-haiku-4-5"}
        v = _qg_module.quality_gate("restructure_merge", "input", "output", config)

        assert v.verdict == Verdict.FAIL
        assert v.passed is False
        assert v.suggest_retry is True
        assert v.suggested_model == "claude-sonnet-4-5-20250514"

    @patch.object(_qg_module, "call_model")
    @patch.object(_qg_module, "load_prompt")
    def test_uncertain_verdict(self, mock_prompt, mock_model):
        mock_prompt.return_value = "Judge prompt for {operation}"
        mock_model.return_value = json.dumps({
            "passed": True, "confidence": 0.6,
            "rationale": "Borderline grouping", "issues": ["weak connection"]
        })

        config = {"model": "claude-haiku-4-5"}
        v = _qg_module.quality_gate("restructure_merge", "input", "output", config)

        assert v.verdict == Verdict.UNCERTAIN
        assert v.passed is False
        assert v.suggest_retry is True

    @patch.object(_qg_module, "call_model")
    @patch.object(_qg_module, "load_prompt")
    def test_uses_judge_model(self, mock_prompt, mock_model):
        mock_prompt.return_value = "Judge prompt for {operation}"
        mock_model.return_value = json.dumps({
            "passed": True, "confidence": 0.95, "rationale": "ok", "issues": []
        })

        config = {"model": "claude-haiku-4-5", "judge_model": "claude-sonnet-4-5-20250514"}
        _qg_module.quality_gate("enrich", "input", "output", config)

        call_args = mock_model.call_args
        judge_config = call_args[0][2]
        assert judge_config["model"] == "claude-sonnet-4-5-20250514"

    @patch.object(_qg_module, "call_model")
    @patch.object(_qg_module, "load_prompt")
    def test_backend_error_returns_uncertain(self, mock_prompt, mock_model):
        mock_prompt.return_value = "Judge prompt for {operation}"
        mock_model.side_effect = BackendError("connection refused")

        config = {"model": "claude-haiku-4-5"}
        v = _qg_module.quality_gate("review_promote", "input", "output", config)

        assert v.verdict == Verdict.UNCERTAIN
        assert v.passed is False
        assert v.confidence == 0.0
        assert v.suggest_retry is True
        assert "failed" in v.rationale.lower()
