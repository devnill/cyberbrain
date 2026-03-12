"""
quality_gate.py

LLM-as-judge quality gate for curation tool output. Called internally by
curation tools (restructure, enrich, review) to validate output before
committing. The user never interacts with this directly.
"""

import json
import sys
from dataclasses import dataclass
from enum import Enum

from cyberbrain.extractors.backends import call_model, BackendError, get_judge_model
from cyberbrain.extractors.config import load_prompt


class Verdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    UNCERTAIN = "uncertain"


@dataclass
class GateVerdict:
    verdict: Verdict
    passed: bool  # True only when verdict == PASS
    confidence: float  # 0.0-1.0
    rationale: str
    issues: list  # specific issues identified by the judge
    suggest_retry: bool = False
    suggested_model: str = ""  # if retry recommended with stronger model


def quality_gate(
    operation: str,
    input_context: str,
    output: str,
    config: dict,
) -> GateVerdict:
    """Evaluate curation output via LLM-as-judge.

    Args:
        operation: Type of curation operation (e.g. "restructure_merge",
                   "enrich", "review_promote"). Used to select evaluation
                   criteria in the judge prompt.
        input_context: What was given to the curation model.
        output: What the curation model produced.
        config: Global config dict. Uses judge_model if set, else model.

    Returns:
        GateVerdict with pass/fail/uncertain decision, confidence, and rationale.
    """
    system_prompt = load_prompt("quality-gate-system.md")
    system_prompt = system_prompt.replace("{operation}", operation)

    user_message = (
        f"## Input Context\n\n{input_context}\n\n"
        f"## Tool Output\n\n{output}"
    )

    judge_config = {**config, "model": get_judge_model(config)}

    try:
        raw = call_model(system_prompt, user_message, judge_config)
    except BackendError as e:
        print(f"[quality_gate] LLM call failed: {e}", file=sys.stderr)
        return GateVerdict(
            verdict=Verdict.UNCERTAIN,
            passed=False,
            confidence=0.0,
            rationale=f"Quality gate LLM call failed: {e}",
            issues=[],
            suggest_retry=True,
        )

    return _parse_verdict(raw, config)


def _parse_verdict(raw: str, config: dict) -> GateVerdict:
    """Parse the LLM judge response into a GateVerdict."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        print(f"[quality_gate] Failed to parse judge response as JSON: {text[:200]}", file=sys.stderr)
        return GateVerdict(
            verdict=Verdict.UNCERTAIN,
            passed=False,
            confidence=0.0,
            rationale="Quality gate response was not valid JSON",
            issues=[],
            suggest_retry=True,
        )

    passed = bool(data.get("passed", False))
    confidence = float(data.get("confidence", 0.0))
    confidence = max(0.0, min(1.0, confidence))  # clamp
    rationale = str(data.get("rationale", "No rationale provided"))
    suggest_retry = bool(data.get("suggest_retry", False))
    issues = list(data.get("issues", []))

    # Determine verdict from confidence thresholds
    if passed and confidence >= 0.7:
        verdict = Verdict.PASS
    elif not passed:
        verdict = Verdict.FAIL
        suggest_retry = True
    else:
        # passed but low confidence — uncertain
        verdict = Verdict.UNCERTAIN
        suggest_retry = True

    # Suggest model escalation for failures on cheap models
    suggested_model = ""
    if suggest_retry and verdict == Verdict.FAIL:
        current_model = config.get("model", "")
        if "haiku" in current_model.lower():
            suggested_model = "claude-sonnet-4-5-20250514"

    return GateVerdict(
        verdict=verdict,
        passed=(verdict == Verdict.PASS),
        confidence=confidence,
        rationale=rationale,
        issues=issues,
        suggest_retry=suggest_retry,
        suggested_model=suggested_model,
    )
